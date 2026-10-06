from flask import Flask, render_template, jsonify, request, session, redirect
import sqlite3

app = Flask(__name__)

app.secret_key = "pharmacy-secret-key-123"

DATABASE = "pharmacy.db"

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if username == "admin" and password == "admin123":

            session["logged_in"] = True
            session["username"] = username

            return redirect("/dashboard")

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def create_database():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Medicines table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_name TEXT NOT NULL UNIQUE,
            salt_1 TEXT NOT NULL,
            salt_2 TEXT
        )
    """)
    # Add price column if it does not already exist
    columns = [
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(medicines)"
        ).fetchall()
    ]

    if "price" not in columns:
        connection.execute("""
            ALTER TABLE medicines
            ADD COLUMN price REAL DEFAULT 0
        """)

    # Drug interactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drug_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            salt_1 TEXT NOT NULL,
            salt_2 TEXT NOT NULL,
            severity TEXT NOT NULL,
            action TEXT NOT NULL,
            message TEXT NOT NULL
        )
    """)
    # Sales / Prescription records table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_number TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            total_amount REAL DEFAULT 0,
            interaction_found INTEGER DEFAULT 0,
            sale_allowed INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Medicine data
    medicines = [
        ("Augmentin 625", "Amoxicillin", "Clavulanic Acid", 25.00),
        ("Augmentin 1g", "Amoxicillin", "Clavulanic Acid", 35.00),
        ("Azithral 500", "Azithromycin", None, 18.00),
        ("Ciplox 500", "Ciprofloxacin", None, 12.00),
        ("Paracetamol 500", "Paracetamol", None, 5.00),
        ("Paracetamol 650", "Paracetamol", None, 7.00),
        ("Metformin 500", "Metformin", None, 10.00),
        ("Warfarin", "Warfarin", None, 20.00)
    ]

    for medicine in medicines:
        try:
            cursor.execute("""
                INSERT INTO medicines
                (brand_name, salt_1, salt_2, price)
                VALUES (?, ?, ?, ?)
            """, medicine)
        except sqlite3.IntegrityError:
            pass

    # Update prices for existing medicines
    prices = ({
        "Augmentin 625": 25.00,
        "Augmentin 1g": 35.00,
        "Azithral 500": 18.00,
        "Ciplox 500": 12.00,
        "Paracetamol 500": 5.00,
        "Paracetamol 650": 7.00,
        "Metformin 500": 10.00,
        "Warfarin": 20.00
    })
    for brand_name, price in prices.items():
        cursor.execute("""
            UPDATE medicines
            SET price = ?
            WHERE brand_name = ?
        """, (price, brand_name))
    connection.commit()
    connection.close()
@app.route("/")
def home():

    if session.get("logged_in"):
        return redirect("/dashboard")

    return redirect("/login")
@app.route("/dashboard")
def dashboard():

    if not session.get("logged_in"):
        return redirect("/login")

    return render_template("index.html")

@app.route("/api/dashboard-stats")
def dashboard_stats():

    connection = get_db_connection()

    total_prescriptions = connection.execute("""
        SELECT COUNT(*) AS count
        FROM sales
    """).fetchone()["count"]

    interactions_found = connection.execute("""
        SELECT COUNT(*) AS count
        FROM sales
        WHERE interaction_found = 1
    """).fetchone()["count"]

    blocked_sales = connection.execute("""
        SELECT COUNT(*) AS count
        FROM sales
        WHERE sale_allowed = 0
    """).fetchone()["count"]

    todays_sales = connection.execute("""
        SELECT COALESCE(SUM(total_amount), 0) AS total
        FROM sales
        WHERE sale_allowed = 1
        AND DATE(created_at, 'localtime')
            = DATE('now', 'localtime')
    """).fetchone()["total"]

    connection.close()

    return jsonify({
        "total_prescriptions": total_prescriptions,
        "interactions_found": interactions_found,
        "blocked_sales": blocked_sales,
        "todays_sales": todays_sales
    })
@app.route("/prescription")
def prescription():

    if not session.get("logged_in"):
        return redirect("/login")

    return render_template("prescription.html")


@app.route("/api/medicines")
def get_medicines():
    connection = get_db_connection()

    medicines = connection.execute("""
        SELECT * FROM medicines
        ORDER BY brand_name
    """).fetchall()

    connection.close()

    return jsonify([dict(medicine) for medicine in medicines])


@app.route("/api/medicine/<int:medicine_id>")
def get_medicine(medicine_id):
    connection = get_db_connection()

    medicine = connection.execute("""
        SELECT * FROM medicines
        WHERE id = ?
    """, (medicine_id,)).fetchone()

    connection.close()

    if medicine is None:
        return jsonify({"error": "Medicine not found"}), 404

    return jsonify(dict(medicine))




@app.route("/api/interactions")
def get_interactions():
    connection = get_db_connection()

    interactions = connection.execute("""
        SELECT * FROM drug_interactions
        ORDER BY severity DESC
    """).fetchall()

    connection.close()

    return jsonify([dict(interaction) for interaction in interactions])


@app.route("/api/check-interaction", methods=["GET"])
def check_interaction():
    salt_1 = request.args.get("salt_1")
    salt_2 = request.args.get("salt_2")

    if not salt_1 or not salt_2:
        return jsonify({
            "error": "Both salts are required"
        }), 400

    connection = get_db_connection()

    interaction = connection.execute("""
        SELECT *
        FROM drug_interactions
        WHERE
            (salt_1 = ? AND salt_2 = ?)
            OR
            (salt_1 = ? AND salt_2 = ?)
    """, (salt_1, salt_2, salt_2, salt_1)).fetchone()

    connection.close()

    if interaction is None:
        return jsonify({
            "interaction": False,
            "message": "No interaction found"
        })

    return jsonify({
        "interaction": True,
        "id": interaction["id"],
        "salt_1": interaction["salt_1"],
        "salt_2": interaction["salt_2"],
        "severity": interaction["severity"],
        "action": interaction["action"],
        "message": interaction["message"]
    })

@app.route("/api/check-prescription", methods=["POST"])
def check_prescription():
    data = request.get_json()

    if not data or "salts" not in data:
        return jsonify({
            "error": "Salt list is required"
        }), 400

    salts = data["salts"]

    if len(salts) < 2:
        return jsonify({
            "interactions": [],
            "message": "At least two salts are required"
        })

    connection = get_db_connection()

    found_interactions = []

    # Check every possible pair of salts
    for i in range(len(salts)):
        for j in range(i + 1, len(salts)):

            salt_1 = salts[i]
            salt_2 = salts[j]

            interaction = connection.execute("""
                SELECT *
                FROM drug_interactions
                WHERE
                    (salt_1 = ? AND salt_2 = ?)
                    OR
                    (salt_1 = ? AND salt_2 = ?)
            """, (salt_1, salt_2, salt_2, salt_1)).fetchone()

            if interaction:
                found_interactions.append({
                    "salt_1": interaction["salt_1"],
                    "salt_2": interaction["salt_2"],
                    "severity": interaction["severity"],
                    "action": interaction["action"],
                    "message": interaction["message"]
                })

    connection.close()

    sale_allowed = True

    for interaction in found_interactions:
        if interaction["severity"] == "Severe":
            sale_allowed = False
            break

    return jsonify({
        "interactions": found_interactions,
        "sale_allowed": sale_allowed
    })
@app.route("/bill")
def bill():
    return render_template("bill.html")
@app.route("/interaction-report")
def interaction_report():
    return render_template("interaction_report.html")
@app.route("/api/save-sale", methods=["POST"])
def save_sale():

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Sale data is required"
        }), 400

    prescription_number = data.get("prescriptionNumber")
    patient_name = data.get("patientName")
    total_amount = data.get("totalAmount", 0)
    interaction_found = data.get("interactionFound", 0)
    sale_allowed = data.get("saleAllowed", 1)

    if not prescription_number or not patient_name:
        return jsonify({
            "error": "Prescription number and patient name are required"
        }), 400

    connection = get_db_connection()

    connection.execute("""
        INSERT INTO sales (
            prescription_number,
            patient_name,
            total_amount,
            interaction_found,
            sale_allowed
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        prescription_number,
        patient_name,
        total_amount,
        interaction_found,
        sale_allowed
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True,
        "message": "Sale recorded successfully"
    })
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")
if __name__ == "__main__":
    create_database()
    app.run(debug=True)