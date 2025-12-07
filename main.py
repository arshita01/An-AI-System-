from flask import Flask, request, render_template, jsonify
import pandas as pd
import json
import os
from io import BytesIO
import PyPDF2
from docx import Document
import google.generativeai as genai
from functools import lru_cache
import time
from dotenv import load_dotenv
import logging
import retrying
import re
import bleach

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configure Gemini API
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("Gemini API configured successfully")
except Exception as e:
    logger.error(f"Failed to configure Gemini API: {str(e)}")
    raise

# Cache for file metadata
@lru_cache(maxsize=1)
def get_file_metadata(file_hash):
    global current_content
    logger.debug("Generating file metadata")
    try:
        if isinstance(current_content, pd.DataFrame):
            df = current_content
            return {
                'type': 'dataset',
                'columns': df.columns.tolist(),
                'row_count': len(df),
                'sample_data': df.head(10).to_json(orient='records'),
                'stats': df.describe(include='all').to_json()
            }
        else:
            # Limit text content to avoid token limits
            content = current_content[:20000]
            return {
                'type': 'text',
                'content': content,
                'length': len(content)
            }
    except Exception as e:
        logger.error(f"Error generating metadata: {str(e)}")
        return {'type': 'error', 'message': str(e)}

# Function to parse different file types
def parse_file(file_stream, file_type):
    logger.debug(f"Parsing file of type: {file_type}")
    try:
        if file_type == 'csv':
            return pd.read_csv(file_stream), 'dataset'
        elif file_type == 'xlsx':
            return pd.read_excel(file_stream), 'dataset'
        elif file_type == 'json':
            data = json.load(file_stream)
            return pd.DataFrame(data), 'dataset'
        elif file_type in ['pdf', 'docx', 'txt']:
            if file_type == 'pdf':
                reader = PyPDF2.PdfReader(file_stream)
                text = ''
                for page in reader.pages:
                    text += (page.extract_text() or '') + '\n'
            elif file_type == 'docx':
                doc = Document(file_stream)
                text = '\n'.join([para.text for para in doc.paragraphs])
            else:
                text = file_stream.read().decode('utf-8', errors='ignore')
            return text, 'text'
        else:
            raise ValueError("Unsupported file type")
    except Exception as e:
        logger.error(f"Failed to parse file: {str(e)}")
        raise Exception(f"Failed to parse file: {str(e)}")

# Retry decorator for Gemini API calls
@retrying.retry(
    stop_max_attempt_number=3,
    wait_fixed=2000,
    retry_on_exception=lambda e: isinstance(e, Exception)
)
def call_gemini(context):
    try:
        response = model.generate_content(context)
        ai_output = response.text.strip()
        # Attempt to validate JSON
        json.loads(ai_output)
        return response
    except json.JSONDecodeError:
        logger.warning(f"Gemini response is not valid JSON: {ai_output[:200]}...")
        # Return raw response for fallback processing
        return type('obj', (), {'text': ai_output})
    except Exception as e:
        logger.warning(f"Gemini API call failed: {str(e)}")
        raise

# AI-powered query processing using Gemini
def ai_process_query(content, query, content_type):
    logger.debug(f"Processing query: {query}, content_type: {content_type}")
    file_hash = hash(str(content))
    metadata = get_file_metadata(file_hash)
    if metadata.get('type') == 'error':
        return {
            'status': 'error',
            'result': {
                'type': 'error',
                'message': metadata['message'],
                'description': 'Failed to generate metadata.',
                'natural_language': f'<p style="color: red;"><b>Error:</b> {metadata["message"]}</p>'
            }
        }

    # Escape query for HTML safety
    query_safe = query.replace('<', '&lt;').replace('>', '&gt;')

    # Detect graph queries
    graph_keywords = ["graph", "plot", "chart", "visualize", "graphical", "representation", "diagram"]
    is_graph = any(word in query.lower() for word in graph_keywords)

    if content_type == 'dataset':
        context = f"""
        You are an AI data analyst. The uploaded file is a dataset with columns: {metadata['columns']}. Sample data: {metadata['sample_data']}. Stats: {metadata['stats']}. User query: {query}.
        Analyze the dataset and respond based on the query.
        Return valid JSON only:
        {{"type": "summary|chart|report|extraction|custom|error", "data": {{...}}, "description": "plain text description", "natural_language": "HTML formatted string with <p> for paragraphs, <b> for bold, <ul><li> for points, no markdown"}}
        - For summary: provide detailed analysis of the dataset content, including key insights, trends, statistics for each column.
        - For chart: include chart_type (bar|line|pie), x_column, y_column, data (leave labels and values empty for backend to fill).
        - For report: full data as list of records.
        - For extraction: key-value pairs.
        - For custom: any query-specific analysis.
        - For error: provide message.
        The 'natural_language' must be a well-formatted HTML string using <p>, <b>, <ul>, <li> tags, starting with '<p><b>Analysis for \"{query_safe}\":</b></p>', tailored to the query, focusing on content details.
        Ensure the response is valid JSON. Do not include ```json or other markers.
        """
    else:
        context = f"""
        You are an AI document analyst. The uploaded file is a text document with content: {metadata['content']}. User query: {query}.
        Analyze the document and respond based on the query.
        Return valid JSON only:
        {{"type": "summary|report|extraction|custom|error", "data": {{...}}, "description": "plain text description", "natural_language": "HTML formatted string with <p> for paragraphs, <b> for bold, <ul><li> for points, no markdown"}}
        - For summary: provide detailed summary of the document content, including all key details, sections, entities, without metadata like length.
        - For report: full text in data.text.
        - For extraction: key-value pairs (e.g., {{"name": "value"}}).
        - For custom: any query-specific analysis.
        - No charts for text.
        The 'natural_language' must be a well-formatted HTML string using <p>, <b>, <ul>, <li> tags, starting with '<p><b>Analysis for \"{query_safe}\":</b></p>', tailored to the query, focusing on content details.
        Ensure the response is valid JSON. Do not include ```json or other markers.
        """

    try:
        response = call_gemini(context)
        ai_output = response.text.strip()
        logger.debug(f"Gemini response: {ai_output[:200]}...")

        try:
            result = json.loads(ai_output)
            # Validate and adjust for chart data if needed
            if content_type == 'dataset' and (result.get('type') == 'chart' or is_graph):
                x_col = result.get('data', {}).get('x_column')
                y_col = result.get('data', {}).get('y_column')
                if x_col in content.columns and y_col in content.columns:
                    result['data']['labels'] = content[x_col].astype(str).tolist()[:100]
                    result['data']['values'] = content[y_col].tolist()[:100]
                    result['data']['chart_type'] = result.get('data', {}).get('chart_type', 'bar')
                else:
                    # Fallback to graph prompt for explicit chart queries
                    graph_prompt = f"""
                    You are an expert in extracting data for chart generation from dataset content.
                    The user has asked: "{query}"
                    The dataset has columns: {metadata['columns']}. Sample data: {metadata['sample_data']}.
                    Instructions:
                    1. Identify data to visualize (e.g., categories and values).
                    2. Return a valid JSON string with 'labels' (categories), 'data' (values), and 'chart_type' (bar|line|pie).
                    3. If no suitable data is found, return '{{"labels": [], "data": [], "chart_type": "bar"}}'.
                    4. Ensure JSON is well-formed and suitable for a chart.
                    Return valid JSON only:
                    {{"labels": [], "data": [], "chart_type": "bar|line|pie"}}
                    """
                    graph_response = call_gemini(graph_prompt).text.strip()
                    try:
                        json_match = re.search(r'\{.*\}', graph_response, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(0)
                        else:
                            json_str = graph_response
                        chart_data = json.loads(json_str)
                        labels = chart_data.get('labels', [])
                        data = chart_data.get('data', [])
                        chart_type = chart_data.get('chart_type', 'bar')
                        if labels and data and len(labels) == len(data):
                            result = {
                                'type': 'chart',
                                'data': {
                                    'labels': labels,
                                    'values': data,
                                    'chart_type': chart_type
                                },
                                'description': f'Chart for {query}',
                                'natural_language': f'<p><b>Analysis for "{query_safe}":</b> Displaying {chart_type} chart.</p>'
                            }
                        else:
                            result = {
                                'type': 'error',
                                'message': 'No suitable data for chart.',
                                'description': 'No comparable numerical data found.',
                                'natural_language': f'<p style="color: red;"><b>Error:</b> No suitable data found for chart.</p>'
                            }
                    except json.JSONDecodeError as e:
                        result = {
                            'type': 'error',
                            'message': f'Failed to generate chart: {str(e)}',
                            'description': 'Invalid chart data format.',
                            'natural_language': f'<p style="color: red;"><b>Error:</b> Failed to generate chart: {str(e)}</p>'
                        }
            elif content_type == 'dataset' and result.get('type') == 'report':
                result['data'] = content.to_dict(orient='records')[:100]
            elif content_type == 'text' and result.get('type') == 'report':
                result['data'] = {'text': content[:10000]}

            # Ensure natural_language is valid HTML
            if 'natural_language' not in result or not result['natural_language'].strip():
                result['natural_language'] = f'<p><b>Analysis for "{query_safe}":</b> {result.get("description", "No details available.")}</p>'
            elif not ('<p>' in result['natural_language'] or '<ul>' in result['natural_language']):
                result['natural_language'] = f'<p><b>Analysis for "{query_safe}":</b> {result["natural_language"]}</p>'
            elif not result['natural_language'].startswith(f'<p><b>Analysis for "{query_safe}":</b>'):
                result['natural_language'] = f'<p><b>Analysis for "{query_safe}":</b></p>' + result['natural_language']

            if result.get('type') == 'error':
                logger.warning(f"Gemini returned error: {result.get('message')}")
                return {'status': 'error', 'result': result}
            logger.info(f"Query processed successfully: {query}")
            return {'status': 'success', 'result': result}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {str(e)}, full response: {ai_output}")
            # Convert non-JSON response to HTML
            escaped_output = bleach.clean(ai_output.replace('\n', '<br>'), tags=['p', 'br', 'b', 'ul', 'li'])
            result = {
                'type': 'summary',
                'data': {'text': ai_output[:10000]},
                'description': 'Fallback response due to invalid JSON.',
                'natural_language': f'<p><b>Analysis for "{query_safe}":</b> Gemini response was not valid JSON. Displaying raw content:</p><p>{escaped_output}</p>'
            }
            logger.warning("Using fallback response due to invalid JSON")
            return {'status': 'success', 'result': result}
    except Exception as e:
        logger.error(f"AI processing failed: {str(e)}, full response: {ai_output if 'ai_output' in locals() else 'No response'}")
        result = {
            'type': 'error',
            'message': str(e),
            'description': 'AI processing failed.',
            'natural_language': f'<p style="color: red;"><b>Error:</b> {str(e)}</p>'
        }
        return {'status': 'error', 'result': result}

@app.route('/')
def index():
    logger.debug("Rendering index.html")
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    logger.debug("Received file upload request")
    if 'file' not in request.files:
        logger.warning("No file part in request")
        return jsonify({
            'status': 'error',
            'message': 'No file part',
            'natural_language': '<p style="color: red;"><b>Error:</b> No file included in the request.</p>'
        })
    file = request.files['file']
    if file.filename == '':
        logger.warning("No file selected")
        return jsonify({
            'status': 'error',
            'message': 'No selected file',
            'natural_language': '<p style="color: red;"><b>Error:</b> No file selected for upload.</p>'
        })
    file_type = file.filename.split('.')[-1].lower()
    logger.info(f"Uploading file: {file.filename}, type: {file_type}")
    try:
        file_stream = BytesIO(file.read())
        parsed_content, parsed_type = parse_file(file_stream, file_type)
        global current_content, current_content_type
        current_content = parsed_content
        current_content_type = parsed_type
        get_file_metadata.cache_clear()
        logger.info("File uploaded successfully")
        return jsonify({
            'status': 'success',
            'message': 'File processed successfully',
            'natural_language': f'<p class="text-green-400 font-semibold text-lg animate-pulse"><b>Success:</b> File uploaded as {parsed_type}.</p>'
        })
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'natural_language': f'<p style="color: red;"><b>Error:</b> {str(e)}</p>'
        })

@app.route('/query', methods=['POST'])
def handle_query():
    query = request.json.get('query')
    logger.debug(f"Received query: {query}")
    if not query:
        logger.warning("No query provided")
        return jsonify({
            'status': 'error',
            'message': 'No query provided',
            'natural_language': '<p style="color: red;"><b>Error:</b> No query provided in the request.</p>'
        })
    try:
        global current_content, current_content_type
        if 'current_content' not in globals() or current_content is None:
            logger.warning("No file uploaded before query")
            return jsonify({
                'status': 'error',
                'message': 'Upload a file first',
                'natural_language': '<p style="color: red;"><b>Error:</b> Please upload a file first.</p>'
            })
        start_time = time.time()
        result = ai_process_query(current_content, query, current_content_type)
        logger.info(f"Query processing time: {time.time() - start_time:.2f} seconds")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Query handling failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'natural_language': f'<p style="color: red;"><b>Error:</b> {str(e)}</p>'
        })

if __name__ == '__main__':
    logger.info("Starting Flask app")
    app.run(debug=True)