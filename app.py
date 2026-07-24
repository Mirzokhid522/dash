import os
import requests
from flask import Flask, render_template
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_KEYS = ["DB_USD", "DB_AUD", "DB_EUR", "DB_GBP", "DB_CAD", "DB_CHF", "DB_JPY"]

# Standard global market hierarchy for tradeable forex pairs
FX_HIERARCHY = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

@app.route("/")
def dashboard():
    debug_logs = []
    debug_logs.append(f"Token Present: {bool(NOTION_TOKEN)}")

    currencies = {} 
    
    if not NOTION_TOKEN:
        debug_logs.append("Error: Missing Notion Token.")
    else:
        for db_key in DB_KEYS:
            db_id = os.getenv(db_key)
            if not db_id:
                continue
            
            # Use database key name as fallback currency code (e.g., DB_USD -> USD)
            fallback_code = db_key.replace("DB_", "")
            
            url = f"https://api.notion.com/v1/databases/{db_id}/query"
            try:
                response = requests.post(url, headers=HEADERS, timeout=5)
                debug_logs.append(f"{db_key} Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    
                    for page in results:
                        props = page.get("properties", {})
                        
                        curr_name = fallback_code
                        score = 0.0
                        bias = "Neutral"

                        for prop_name, prop_data in props.items():
                            p_type = prop_data.get("type")
                            
                            # 1. Title property
                            if p_type == "title":
                                t_list = prop_data.get("title", [])
                                if t_list and t_list[0].get("plain_text", "").strip():
                                    curr_name = t_list[0].get("plain_text").strip().upper()

                            # 2. Extract Score (Rollup, Number, or Formula)
                            elif prop_name in ["Score", "Final Score"]:
                                if p_type == "rollup":
                                    score = prop_data.get("rollup", {}).get("number") or 0.0
                                elif p_type == "number":
                                    score = prop_data.get("number") or 0.0
                                elif p_type == "formula":
                                    score = prop_data.get("formula", {}).get("number") or 0.0

                            # 3. Extract Bias from Formula or Select/Status
                            elif prop_name == "Bias":
                                if p_type == "formula":
                                    f_data = prop_data.get("formula", {})
                                    if f_data.get("type") == "string":
                                        bias = f_data.get("string", "Neutral")
                                elif p_type == "select":
                                    bias = prop_data.get("select", {}).get("name", "Neutral")
                                elif p_type == "status":
                                    bias = prop_data.get("status", {}).get("name", "Neutral")

                        currencies[curr_name] = {
                            "score": float(score),
                            "bias": bias
                        }
                else:
                    debug_logs.append(f"{db_key} Error: {response.status_code}")
            except requests.exceptions.Timeout:
                debug_logs.append(f"Error: {db_key} request timed out.")
            except Exception as e:
                debug_logs.append(f"Exception on {db_key}: {e}")

    debug_logs.append(f"Parsed Currencies: {list(currencies.keys())}")

    # Generate standard tradeable pairs & calculate differential scores using market hierarchy
    derived_pairs = []
    available_currs = list(currencies.keys())
    
    for i in range(len(available_currs)):
        for j in range(len(available_currs)):
            curr_a = available_currs[i]
            curr_b = available_currs[j]
            
            if curr_a == curr_b:
                continue
                
            try:
                pos_a = FX_HIERARCHY.index(curr_a)
                pos_b = FX_HIERARCHY.index(curr_b)
            except ValueError:
                continue  # Skip currencies not recognized in the hierarchy
                
            # Enforce institutional market hierarchy (Base / Quote)
            if pos_a < pos_b:
                base = curr_a
                quote = curr_b
            else:
                base = curr_b
                quote = curr_a
                
            pair_symbol = f"{base}{quote}"
            
            # Prevent duplicate pairs
            if any(item['symbol'] == pair_symbol for item in derived_pairs):
                continue
            
            base_score = currencies[base]["score"]
            quote_score = currencies[quote]["score"]
            
            diff_score = round(base_score - quote_score, 4)
            
            # Dynamic bias threshold mapping
            if diff_score >= 2.0:
                pair_bias = "Very Bullish"
            elif diff_score > 0.0:
                pair_bias = "Bullish"
            elif diff_score == 0.0:
                pair_bias = "Neutral"
            elif diff_score > -2.0:
                pair_bias = "Bearish"
            else:
                pair_bias = "Very Bearish"

            derived_pairs.append({
                "symbol": pair_symbol,
                "score": diff_score,
                "bias": pair_bias
            })

    # Sort descending by differential score
    derived_pairs = sorted(derived_pairs, key=lambda x: x["score"], reverse=True)

    return render_template("index.html", derived_pairs=derived_pairs, debug_logs=debug_logs)

if __name__ == "__main__":
    app.run(debug=True)