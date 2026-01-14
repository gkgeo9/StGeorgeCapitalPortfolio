# St George Capital Portfolio Manager

This project is a Flask-based portfolio management application that tracks stocks using yfinance or Alpha Vantage.

## Prerequisites

- Python 3.11+
- Virtual environment (see below)

## Setup Instructions

Based on the project requirements, you should use the virtual environment located in the sibling project folder:
`C:\Users\vdocv\PycharmProjects\StGeorgeCapital\venv`

### 1. Project Dependencies

The dependencies have already been installed into the shared virtual environment. If you need to reinstall them, run:

```powershell
& "C:\Users\vdocv\PycharmProjects\StGeorgeCapital\venv\Scripts\python.exe" -m pip install -r requirements.txt
```

### 2. Environment Variables

The application can be configured via environment variables. You can create a `.env` file in this directory with the following options:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///portfolio.db
PRICE_PROVIDER=yfinance  # Options: auto, yfinance, alphavantage
ALPHA_VANTAGE_API_KEY=your-api-key (optional)
```

### 3. How to Run

To start the application, use the following command in your terminal:

```powershell
# Set the Flask App entry point
$env:FLASK_APP="app.py"

# Run using the shared virtual environment
& "C:\Users\vdocv\PycharmProjects\StGeorgeCapital\venv\Scripts\python.exe" -m flask run --port 5012
```

The application will be available at: [http://127.0.0.1:5012](http://127.0.0.1:5012)

### 4. Database Initialization

The application automatically initializes the SQLite database (`portfolio.db`) and creates necessary tables on the first run.

## Troubleshooting

- **ModuleNotFoundError**: Ensure you are using the correct path to the `python.exe` in the `StGeorgeCapital\venv` folder.
- **Port already in use**: If port 5012 is taken, you can change it in the run command using `--port <new_port>`.
