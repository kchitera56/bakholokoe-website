from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
from dotenv import load_dotenv
import json
import os

# ------------------------------
# LOAD ENVIRONMENT VARIABLES
# ------------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# ------------------------------
# EMAIL CONFIG
# ------------------------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = ('Bakholokoe Game Lodge', os.getenv("MAIL_USERNAME"))

mail = Mail(app)

def send_email(subject, recipient, body):
    msg = Message(subject, recipients=[recipient])
    msg.body = body
    mail.send(msg)

# ------------------------------
# FIREBASE INITIALIZATION
# ------------------------------
if not firebase_admin._apps:
    firebase_credentials_raw = os.getenv("FIREBASE_CREDENTIALS")

    if not firebase_credentials_raw:
        raise RuntimeError("❌ FIREBASE_CREDENTIALS environment variable missing!")

    try:
        firebase_credentials = json.loads(firebase_credentials_raw)
    except json.JSONDecodeError:
        raise RuntimeError("❌ Invalid FIREBASE_CREDENTIALS JSON format")

    cred = credentials.Certificate(firebase_credentials)

    firebase_admin.initialize_app(cred, {
        "databaseURL": os.getenv("DATABASE_URL")
    })

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------
def format_email_key(email):
    return email.replace('.', '_')

def get_user(email):
    return db.reference(f"users/{format_email_key(email)}").get()

def save_user(email, name, password):
    db.reference(f"users/{format_email_key(email)}").set({
        "name": name,
        "password": password
    })

def save_booking(category, email, data):
    db.reference(f"bookings/{category}").push({
        "user": email,
        **data
    })

def get_all_reviews():
    return list((db.reference("reviews").get() or {}).values())

def save_review(email, name, review, rating):
    db.reference("reviews").push({
        "user": email,
        "name": name,
        "review": review,
        "rating": rating
    })

def save_contact_message(name, email, phone, message):
    db.reference("contact_messages").push({
        "name": name,
        "email": email,
        "phone": phone,
        "message": message,
        "timestamp": datetime.now().isoformat()
    })

def get_all_contact_messages():
    messages = db.reference("contact_messages").get() or {}
    return sorted(messages.values(), key=lambda x: x.get("timestamp", ""), reverse=True)

# ------------------------------
# PUBLIC ROUTES
# ------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/gallery")
def gallery():
    return render_template("gallery.html")

@app.route("/map")
def map_page():
    return render_template("map.html")

@app.route("/kids")
def kids():
    return render_template("kids.html")

# ------------------------------
# CONTACT FORM
# ------------------------------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":

        if "user" in session:
            email = session["user"]
            user_name = get_user(email)["name"]
            phone = ""
        else:
            user_name = request.form.get("first_name")
            email = request.form.get("email")
            phone = request.form.get("phone")

        message = request.form.get("message")
        save_contact_message(user_name, email, phone, message)

        send_email(
            "New Contact Message",
            os.getenv("MAIL_USERNAME"),
            f"Name: {user_name}\nEmail: {email}\nPhone: {phone}\nMessage:\n{message}"
        )

        send_email(
            "We received your message",
            email,
            "Thank you for contacting Bakholokoe Game Reserve. We will reply shortly."
        )

        flash("Your message has been sent!", "success")
        return redirect(url_for("contact"))

    messages = get_all_contact_messages()
    return render_template("contact.html", messages=messages)

# ------------------------------
# REVIEWS
# ------------------------------
@app.route("/reviews", methods=["GET", "POST"])
def reviews_page():
    if request.method == "POST":
        if "user" not in session:
            return redirect(url_for("login"))

        email = session["user"]

        # Only allow 1 review per user
        if any(r["user"] == email for r in get_all_reviews()):
            flash("You have already submitted a review.", "error")
            return redirect(url_for("reviews_page"))

        review = request.form["review"]
        rating = request.form["rating"]
        name = get_user(email)["name"]

        save_review(email, name, review, rating)

        send_email(
            "New Review Submitted",
            os.getenv("MAIL_USERNAME"),
            f"User: {email}\nName: {name}\nRating: {rating}\nReview: {review}"
        )

        flash("Review submitted!", "success")
        return redirect(url_for("reviews_page"))

    return render_template("reviews.html")

# ------------------------------
# AUTHENTICATION
# ------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        if get_user(email):
            flash("User already exists", "error")
            return redirect(url_for("signup"))

        save_user(email, name, password)
        flash("Signup successful!", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    next_page = request.args.get("next")

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = get_user(email)

        if not user or user["password"] != password:
            flash("Incorrect email or password", "error")
            return redirect(url_for("login"))

        session["user"] = email
        flash("Login successful!", "success")
        return redirect(url_for(next_page or "index"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("index"))

# ------------------------------
# HUNT BOOKING
# ------------------------------
@app.route("/book-hunt", methods=["GET", "POST"])
def book_hunt():
    if "user" not in session:
        return redirect(url_for("login", next="book_hunt"))

    email = session["user"]
    success = False

    if request.method == "POST":
        data = {
            "first_name": request.form["first_name"],
            "contact": request.form["contact"],
            "hunt_date": request.form["hunt_date"]
        }

        save_booking("hunt", email, data)

        send_email(
            "New Hunt Booking",
            os.getenv("MAIL_USERNAME"),
            f"User: {email}\nName: {data['first_name']}\nContact: {data['contact']}\nDate: {data['hunt_date']}"
        )

        success = True

    return render_template("book_hunt.html", success=success)

# ------------------------------
# ACCOMMODATION BOOKING
# ------------------------------
@app.route("/accommodation", methods=["GET", "POST"])
def accommodation():
    if "user" not in session:
        return redirect(url_for("login", next="accommodation"))

    email = session["user"]
    success = False

    if request.method == "POST":
        data = {
            "first_name": request.form["first_name"],
            "contact": request.form["contact"],
            "checkin_date": request.form["checkin_date"]
        }

        save_booking("accommodation", email, data)

        send_email(
            "New Accommodation Booking",
            os.getenv("MAIL_USERNAME"),
            f"User: {email}\nName: {data['first_name']}\nContact: {data['contact']}\nCheck-In: {data['checkin_date']}"
        )

        success = True

    return render_template("accommodation.html", success=success)

# ------------------------------
# PURIFIED WATER
# ------------------------------
@app.route("/purified-water", methods=["GET", "POST"])
def water():
    if "user" not in session:
        return redirect(url_for("login", next="water"))

    email = session["user"]
    success = False

    if request.method == "POST":
        data = {
            "first_name": request.form["first_name"],
            "contact": request.form["contact"],
            "product_quantity": request.form["product_quantity"],
            "location": request.form["location"]
        }

        save_booking("water", email, data)

        send_email(
            "New Water Order",
            os.getenv("MAIL_USERNAME"),
            f"User: {email}\nName: {data['first_name']}\nContact: {data['contact']}\nOrder: {data['product_quantity']}\nLocation: {data['location']}"
        )

        success = True

    return render_template("water.html", success=success)

# ------------------------------
# RUN SERVER
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
