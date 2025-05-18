from flask import Flask, request, jsonify, send_from_directory
from flask_pymongo import PyMongo
from flask_cors import CORS
import jwt
import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flask app setup
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")

# CORS config
CORS(app, resources={r"/api/*": {"origins": "https://paruluniversityevents.netlify.app"}})

# MongoDB
mongo = PyMongo(app)


# ---------------------- AUTH ROUTES ----------------------

@app.route("/api/users/create", methods=["POST"])
def create_account():
    try:
        if not request.is_json:
            return jsonify({"message": "Invalid request: JSON data required"}), 400

        data = request.get_json()
        enrollment = data.get("enrollment")
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        role = data.get("role", "user")

        if not all([enrollment, name, email, password]):
            return jsonify({"message": "All fields are required!"}), 400

        if "@" not in email or "." not in email:
            return jsonify({"message": "Invalid email format!"}), 400
        if len(password) < 6:
            return jsonify({"message": "Password must be at least 6 characters!"}), 400

        existing_user = mongo.db.users.find_one({"enrollment": enrollment})
        if existing_user:
            return jsonify({"message": "User with this enrollment already exists!"}), 400

        new_user = {
            "enrollment": enrollment,
            "name": name,
            "email": email,
            "password": password,
            "role": role
        }
        result = mongo.db.users.insert_one(new_user)

        if result.inserted_id:
            return jsonify({"message": "Account created successfully!"}), 201
        else:
            return jsonify({"message": "Failed to create account"}), 500

    except Exception as e:
        return jsonify({"message": f"Server error: {str(e)}"}), 500


@app.route("/api/users/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        enrollment = data.get("enrollment")
        password = data.get("password")

        if not enrollment or not password:
            return jsonify({"message": "Enrollment and password are required!"}), 400

        user = mongo.db.users.find_one({"enrollment": enrollment})
        if user and user["password"] == password:
            token = jwt.encode({
                "enrollment": enrollment,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2)
            }, app.config["SECRET_KEY"], algorithm="HS256")

            return jsonify({
                "token": token,
                "redirect": "/dashboard",
                "user": {
                    "name": user.get("name"),
                    "role": user.get("role"),
                    "photo": user.get("photo", "")
                }
            }), 200

        return jsonify({"message": "Invalid credentials"}), 401

    except Exception as e:
        return jsonify({"message": f"Server error: {str(e)}"}), 500


@app.route("/api/users/me", methods=["GET"])
def get_user():
    token = request.headers.get("Authorization")
    if not token:
        return jsonify({"message": "Token is missing!"}), 401

    try:
        decoded_token = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        enrollment = decoded_token["enrollment"]
        user = mongo.db.users.find_one({"enrollment": enrollment}, {"_id": 0, "password": 0})
        if user:
            return jsonify(user), 200
        return jsonify({"message": "User not found"}), 404

    except jwt.ExpiredSignatureError:
        return jsonify({"message": "Token expired!"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"message": "Invalid token!"}), 401


# ---------------------- EVENTS ----------------------

@app.route("/api/events/create", methods=["POST"])
def create_event():
    token = request.headers.get("Authorization")
    if not token:
        return jsonify({"message": "Token is missing!"}), 401

    try:
        decoded_token = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        enrollment = decoded_token["enrollment"]
        user = mongo.db.users.find_one({"enrollment": enrollment})

        if not user or user["role"] != "admin":
            return jsonify({"message": "Unauthorized"}), 403

        event_data = request.form.to_dict()
        event_pic = request.files.get("eventPic")

        uploads_dir = "./uploads"
        os.makedirs(uploads_dir, exist_ok=True)

        if event_pic:
            event_pic_filename = f"{event_data['eventName']}_{datetime.datetime.utcnow().timestamp()}.jpg"
            event_pic_path = os.path.join(uploads_dir, event_pic_filename)
            event_pic.save(event_pic_path)
            event_data["eventPic"] = event_pic_filename

        event_data["created_by"] = enrollment
        event_data["isPaid"] = event_data.get("isPaid", "Unpaid")

        mongo.db.CreatedEvent.insert_one(event_data)

        return jsonify({"message": "Event created successfully!"}), 201

    except jwt.ExpiredSignatureError:
        return jsonify({"message": "Token expired!"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"message": "Invalid token!"}), 401
    except Exception as e:
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500


@app.route("/api/events", methods=["GET"])
def get_events():
    try:
        events = list(mongo.db.CreatedEvent.find({}, {"_id": 0}))
        for event in events:
            if "eventDate" in event:
                event["date"] = event["eventDate"]
        return jsonify(events), 200

    except Exception as e:
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500


@app.route("/api/events/register", methods=["POST"])
def register_event():
    token = request.headers.get("Authorization")
    if not token:
        return jsonify({"message": "Token is missing!"}), 401

    try:
        decoded_token = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        enrollment = decoded_token["enrollment"]
        data = request.json

        event_name = data.get("eventName")
        event_date = data.get("eventDate")

        if not event_name or not event_date:
            return jsonify({"message": "Event name and date are required!"}), 400

        existing = mongo.db.RegisteredEvents.find_one({
            "enrollment": enrollment,
            "eventName": event_name
        })
        if existing:
            return jsonify({"message": "You are already registered for this event!"}), 400

        registration = {
            "enrollment": enrollment,
            "eventName": event_name,
            "eventDate": event_date,
            "eventDescription": data.get("eventDescription", ""),
            "department": data.get("department", ""),
            "time": data.get("time", ""),
            "location": data.get("location", ""),
            "isPaid": data.get("isPaid", "Unpaid"),
            "eventPic": data.get("eventPic", ""),
            "registeredAt": datetime.datetime.utcnow()
        }

        mongo.db.RegisteredEvents.insert_one(registration)

        return jsonify({"message": "Successfully registered for the event!"}), 201

    except jwt.ExpiredSignatureError:
        return jsonify({"message": "Token expired!"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"message": "Invalid token!"}), 401
    except Exception as e:
        return jsonify({"message": f"Error registering event: {str(e)}"}), 500


@app.route("/api/users/registered-events", methods=["GET"])
def get_registered_events():
    token = request.headers.get("Authorization")
    if not token:
        return jsonify({"message": "Token is missing!"}), 401

    try:
        decoded_token = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        enrollment = decoded_token["enrollment"]
        user_events = list(mongo.db.RegisteredEvents.find({"enrollment": enrollment}, {"_id": 0}))

        return jsonify({
            "enrollment": enrollment,
            "registeredEvents": user_events,
            "eventCount": len(user_events)
        }), 200

    except jwt.ExpiredSignatureError:
        return jsonify({"message": "Token expired!"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"message": "Invalid token!"}), 401
    except Exception as e:
        return jsonify({"message": f"Error fetching registered events: {str(e)}"}), 500


# ---------------------- UPLOADS ----------------------

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory("./uploads", filename)


# ---------------------- START ----------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
