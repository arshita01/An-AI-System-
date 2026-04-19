**AI Data Analyzer 📊**
An AI-powered web application that lets you upload datasets and documents, ask natural language questions, and get rich insights — including charts, tables, and analysis — powered by **Google Gemini**.
**Features**
- **Multi-format file support** — Upload CSV, Excel (.xlsx), JSON, PDF, Word (.docx), or plain text files
- **Natural language queries** — Ask any question about your data in plain English
- **AI-generated insights** — Gemini analyzes your data and returns formatted, human-readable summaries
- **Interactive visualizations** — Bar, line, and pie charts rendered dynamically via Chart.js
- **Tabular reports** — Structured data extraction displayed in scrollable tables
- **Glassmorphism UI** — Animated, modern frontend with particle effects

##  Tech Stack

| Layer     | Technology                          |
|-----------|--------------------------------------|
| Backend   | Python, Flask                        |
| AI Engine | Google Gemini (`gemini-2.5-flash`)   |
| Frontend  | HTML, Tailwind CSS, JavaScript       |
| Charts    | Chart.js                             |
| Particles | Particles.js                         |
| Parsing   | Pandas, PyPDF2, python-docx          |

### Prerequisites

- Python 3.8+
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)

### Installation

1. **Clone the repository**
```bash
   git clone https://github.com/your-username/ai-data-analyzer.git
   cd ai-data-analyzer
```

2. **Install dependencies**
```bash
   pip install -r requirements.txt
```

3. **Set up environment variables**

   Create a `.env` file in the project root:
```env
   GEMINI_API_KEY=your_gemini_api_key_here
```

4. **Run the app**
```bash
   python app.py
```

5. Open your browser and go to `http://localhost:5000`

## 📦 Requirements

Create a `requirements.txt` with the following:

```
flask
pandas
openpyxl
PyPDF2
python-docx
google-generativeai
python-dotenv
retrying
bleach
```

---

## 📁 Project Structure

```
ai-data-analyzer/
├── app.py                  # Flask backend & Gemini integration
├── templates/
│   └── index.html          # Frontend UI
├── .env                    # API key (not committed)
├── .gitignore
├── requirements.txt
└── README.md
```
## 🧠 How It Works

1. **Upload a file** — The backend parses it into either a Pandas DataFrame (for structured data) or raw text (for documents).
2. **Ask a question** — Your query is sent to Gemini along with the file's content or metadata.
3. **Gemini responds** — The AI returns a structured JSON response specifying the result type: `summary`, `chart`, `report`, `extraction`, or `custom`.
4. **Frontend renders** — The UI displays the natural language answer and, if applicable, allows you to render bar, line, or pie charts.

---

## 🖼️ Supported Query Types

| Query Example                        | Result Type  |
|--------------------------------------|--------------|
| "Summarize this document"            | Summary      |
| "Show me revenue by region as chart" | Chart        |
| "Give me all rows as a table"        | Report       |
| "Extract names and dates"            | Extraction   |
| "What are the top 5 products?"       | Custom       |

## Configuration

| Variable        | Description                     | Required |
|-----------------|---------------------------------|----------|
| `GEMINI_API_KEY`| Your Google Gemini API key      | ✅ Yes   |

##  Security Notes

- User-supplied query strings are HTML-escaped before being injected into Gemini prompts
- Gemini responses are sanitized with `bleach` before rendering as HTML
- File content is held in memory (not persisted to disk)
- Do **not** commit your `.env` file — add it to `.gitignore`

##  Known Limitations

- Only one file can be active at a time (re-upload to switch)
- File content is truncated to 20,000 characters for text documents to stay within Gemini's token limits
- Chart data is capped at 100 rows for performance
- No user authentication or persistent storage

##  Acknowledgements

- [Google Gemini](https://deepmind.google/technologies/gemini/) for the AI backbone
- [Chart.js](https://www.chartjs.org/) for beautiful charts
- [Particles.js](https://vincentgarreau.com/particles.js/) for the animated background
- [Tailwind CSS](https://tailwindcss.com/) for utility-first styling
