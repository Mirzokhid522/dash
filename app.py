import os
import requests
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN")

# Map your currency database IDs
DATABASES = {
    "USD": os.getenv("DB_USD"),
    "AUD": os.getenv("DB_AUD"),
    "EUR": os.getenv("DB_EUR"),
    "GBP": os.getenv("DB_GBP"),
    "CAD": os.getenv("DB_CAD"),
    "CHF": os.getenv("DB_CHF"),
    "JPY": os.getenv("DB_JPY"),
    "NZD": os.getenv("DB_NZD")
}

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/score', methods=['GET'])
def get_macro_score():
    # Default to NZD or USD if no currency is specified, e.g. /api/score?currency=NZD
    currency = request.args.get('currency', 'NZD').upper()
    database_id = DATABASES.get(currency)

    if not database_id:
        return jsonify({"error": f"Invalid or missing database ID for currency: {currency}", "score": 0.0, "status": "Error"}), 400

    try:
        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(url, headers=HEADERS, timeout=5)
        
        if response.status_code != 200:
            print(f"Notion API Error ({currency}): {response.status_code} - {response.text}")
            return jsonify({"error": f"Notion API error {response.status_code}", "score": 0.0, "status": "Error"}), 500

        data = response.json()
        results = data.get("results", [])
        
        total_score = 0.0
        count = 0
        extracted_bias = None

        for page in results:
            props = page.get("properties", {})
            
            for prop_name, prop_data in props.items():
                p_lower = prop_name.lower()
                p_type = prop_data.get("type")

                # 1. Extract Score
                if p_lower in ["score", "final score"]:
                    val = None
                    if p_type == "rollup":
                        val = prop_data.get("rollup", {}).get("number")
                    elif p_type == "number":
                        val = prop_data.get("number")
                    elif p_type == "formula":
                        val = prop_data.get("formula", {}).get("number")

                    if val is not None:
                        total_score += float(val)
                        count += 1

                # 2. Extract Bias
                elif p_lower == "bias":
                    if p_type == "select":
                        extracted_bias = prop_data.get("select", {}).get("name")
                    elif p_type == "status":
                        extracted_bias = prop_data.get("status", {}).get("name")
                    elif p_type == "formula":
                        f_data = prop_data.get("formula", {})
                        if f_data.get("type") == "string":
                            extracted_bias = f_data.get("string")

        score = round(total_score, 4) if count > 0 else 0.0

        if extracted_bias:
            status = extracted_bias
        else:
            if score > 0.3:
                status = "Very Bullish"
            elif score > 0.05:
                status = "Bullish"
            elif score < -0.3:
                status = "Very Bearish"
            elif score < -0.05:
                status = "Bearish"
            else:
                status = "Neutral"

        return jsonify({
            "currency": currency,
            "score": score,
            "status": status
        })

    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({"error": str(e), "score": 0.0, "status": "Error"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)