from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
from dotenv import load_dotenv
import os

# ------------------------------
# LOAD ENVIRONMENT VARIABLES
# ------------------------------
load_dotenv()  # loads variables from .env file

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")  # now loaded from .env

# ------------------------------
# EMAIL CONFIGURATION
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
    cred = credentials.Certificate("firebase_key.json")  # still local, ignore in git
    firebase_admin.initialize_app(cred, {
        "databaseURL": os.getenv("DATABASE_URL")
    })

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------
def get_user(email):
    ref = db.reference(f"users/{email.replace('.', '_')}")
    return ref.get()

def save_user(email, name, password):
    ref = db.reference(f"users/{email.replace('.', '_')}")
    ref.set({"name": name, "password": password})

def save_booking(category, user_email, data):
    ref = db.reference(f"bookings/{category}")
    ref.push({"user": user_email, **data})

def get_user_bookings(category, user_email):
    ref = db.reference(f"bookings/{category}")
    all_bookings = ref.get() or {}
    return [v for k, v in all_bookings.items() if v["user"] == user_email]

def save_review(user_email, name, review_text, rating):
    ref = db.reference("reviews")
    ref.push({"user": user_email, "name": name, "review": review_text, "rating": rating})

def get_all_reviews():
    ref = db.reference("reviews")
    return list((ref.get() or {}).values())

def save_contact_message(name, email, phone, message):
    ref = db.reference("contact_messages")
    ref.push({
        "name": name,
        "email": email,
        "phone": phone,
        "message": message,
        "timestamp": datetime.now().isoformat()
    })

def get_all_contact_messages():
    ref = db.reference("contact_messages")
    all_messages = ref.get() or {}
    return sorted(all_messages.values(), key=lambda x: x.get("timestamp", ""), reverse=True)

# ------------------------------
# PUBLIC ROUTES
# ------------------------------
@app.route("/", endpoint="index")
def index():
    return render_template("index.html")

@app.route("/about", endpoint="about")
def about():
    return render_template("about.html")

@app.route("/gallery", endpoint="gallery")
def gallery():
    return render_template("gallery.html")

@app.route("/map", endpoint="map_page")
def map_page():
    return render_template("map.html")

@app.route("/kids", endpoint="kids")
def kids():
    return render_template("kids.html")

# ------------------------------
# CONTACT PAGE
# ------------------------------
@app.route("/contact", methods=["GET", "POST"], endpoint="contact")
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

        # Email to admin
        admin_body = f"New Contact Message\nName: {user_name}\nEmail: {email}\nPhone: {phone}\nMessage:\n{message}"
        send_email("New Contact Message from Website", os.getenv("MAIL_USERNAME"), admin_body)

        # Auto reply
        send_email("We received your message", email,
                   "Thank you for contacting Bakholokoe Game Reserve. We will reply shortly.")

        flash("Your message has been sent!", "success")
        return redirect(url_for("contact"))

    messages = get_all_contact_messages()
    return render_template("contact.html", messages=messages)

# ------------------------------
# REVIEWS ROUTE
# ------------------------------
@app.route("/reviews", methods=["GET", "POST"], endpoint="reviews")
def reviews_page():
    if request.method == "POST":
        if "user" in session:
            email = session["user"]
            if any(r["user"] == email for r in get_all_reviews()):
                flash("You have already submitted a review.", "error")
            else:
                review = request.form["review"]
                rating = request.form["rating"]
                name = get_user(email)["name"]
                save_review(email, name, review, rating)

                # Notify admin
                send_email(
                    "New Review Submitted",
                    os.getenv("MAIL_USERNAME"),
                    f"User: {email}\nName: {name}\nRating: {rating}\nReview: {review}"
                )

                flash("Review submitted!", "success")
        return redirect(url_for("reviews"))

    # Don't pass reviews to template anymore
    return render_template("reviews.html")

# ------------------------------
# AUTH ROUTES
# ------------------------------
@app.route("/signup", methods=["GET", "POST"], endpoint="signup")
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        if get_user(email):
            flash("User already exists", "error")
            return redirect(url_for("signup"))

        save_user(email, name, password)
        flash("Signup successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"], endpoint="login")
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

@app.route("/logout", endpoint="logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("index"))

# ------------------------------
# SERVICES WITH SUCCESS MESSAGE
# ------------------------------
@app.route("/book-hunt", methods=["GET", "POST"], endpoint="book_hunt")
def book_hunt():
    if "user" not in session:
        return redirect(url_for("login", next="book_hunt"))
    email = session["user"]
    success = False

    if request.method == "POST":
        first = request.form["first_name"]
        contact = request.form["contact"]
        date = request.form["hunt_date"]

        save_booking("hunt", email, {
            "first_name": first,
            "contact": contact,
            "hunt_date": date
        })

        send_email("New Hunt Booking", os.getenv("MAIL_USERNAME"),
                   f"User: {email}\nName: {first}\nContact: {contact}\nDate: {date}")

        success = True

    return render_template("book_hunt.html", success=success)

@app.route("/accommodation", methods=["GET", "POST"], endpoint="accommodation")
def accommodation():
    if "user" not in session:
        return redirect(url_for("login", next="accommodation"))
    email = session["user"]
    success = False

    if request.method == "POST":
        first = request.form["first_name"]
        contact = request.form["contact"]
        date = request.form["checkin_date"]

        save_booking("accommodation", email, {
            "first_name": first,
            "contact": contact,
            "checkin_date": date
        })

        send_email("New Accommodation Booking", os.getenv("MAIL_USERNAME"),
                   f"User: {email}\nName: {first}\nContact: {contact}\nCheck-In: {date}")

        success = True

    return render_template("accommodation.html", success=success)

@app.route("/purified-water", methods=["GET", "POST"], endpoint="water")
def water():
    if "user" not in session:
        return redirect(url_for("login", next="water"))
    email = session["user"]
    success = False

    if request.method == "POST":
        first = request.form["first_name"]
        contact = request.form["contact"]
        qty = request.form["product_quantity"]
        location = request.form["location"]

        save_booking("water", email, {
            "first_name": first,
            "contact": contact,
            "product_quantity": qty,
            "location": location
        })

        send_email("New Water Order", os.getenv("MAIL_USERNAME"),
                   f"User: {email}\nName: {first}\nContact: {contact}\nOrder: {qty}\nDelivery Location: {location}")

        success = True

    return render_template("water.html", success=success)

# ------------------------------
# RUN APP
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
