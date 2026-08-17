from flask import Flask, render_template, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/sales")
def get_sales_data():
    data = [
        {"month": "January", "sales": 50000},
        {"month": "February", "sales": 75000},
        {"month": "March", "sales": 60000},
        {"month": "April", "sales": 90000}
    ]
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)
