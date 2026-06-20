from flask import Flask, render_template, request, redirect, url_for, session, Response, make_response
import os
import csv
import io
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "hack_the_campus_secret_secure_key")

# Initialize Supabase Client (With local mock fallback for previewing)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

use_mock = False
if not SUPABASE_URL or not SUPABASE_KEY:
    print("WARNING: SUPABASE_URL or SUPABASE_KEY is missing. Falling back to local memory MOCK DATABASE for previewing frontend.")
    use_mock = True
else:
    try:
        from supabase import create_client, Client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Failed to connect to Supabase: {e}. Using mock database fallback.")
        use_mock = True

# -----------------------------
# LOCAL MOCK DATABASE SYSTEM FOR PREVIEW
# -----------------------------
mock_teams = {}
mock_progress = []
mock_team_id_seq = 1

# Admin credentials configured from env variables or fallback
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "cyberadmin2026"))

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def get_team_by_id(team_id):
    if use_mock:
        return mock_teams.get(team_id)
    try:
        response = supabase.table("teams").select("*").eq("id", team_id).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        print(f"Error fetching team: {e}")
    return None

def format_seconds(seconds):
    if seconds is None:
        return "N/A"
    if seconds <= 0:
        return "Expired"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{int(minutes)} Min {int(secs)} Sec"

def get_remaining_seconds(team):
    if team.get("completed"):
        return 1500
    
    start_time_str = team.get("start_time")
    if not start_time_str:
        return 1500
        
    try:
        # ISO string parsing
        if isinstance(start_time_str, datetime):
            start_time = start_time_str
        else:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed = (now - start_time).total_seconds()
        remaining = 1500 - int(elapsed)
        return max(0, remaining)
    except Exception as e:
        print(f"Error parsing date {start_time_str}: {e}")
        return 1500

# Enforce route timers and redirects
def verify_session_timer():
    if "team_id" in session:
        team = get_team_by_id(session["team_id"])
        if not team:
            session.clear()
            return redirect(url_for("home_page"))
        
        rem = get_remaining_seconds(team)
        if rem <= 0 and not team.get("completed"):
            return redirect(url_for("mission_failed"))
    return None

# Context processor to inject active team details into templates automatically
@app.context_processor
def inject_team_info():
    if "team_id" in session:
        team = get_team_by_id(session["team_id"])
        if team:
            current_level = team.get("current_level", 1)
            completed = team.get("completed", False)
            score = team.get("score", 0)
            remaining = get_remaining_seconds(team)

            # Compute progress display
            if completed:
                progress_pct = 100
                progress_bar = "■■■■■■■■■■"
                progress_text = "COMPLETED"
            else:
                progress_pct = (current_level - 1) * 20
                if current_level == 5:
                    progress_pct = 90
                
                filled = int(progress_pct / 10)
                empty = 10 - filled
                progress_bar = "■" * filled + "□" * empty
                if current_level == 5:
                    progress_text = "FINAL EXPLoit"
                else:
                    progress_text = f"MISSION {current_level} OF 5"

            return {
                "team_logged_in": True,
                "team_name": team.get("team_name"),
                "leader_name": team.get("leader_name"),
                "current_level": current_level,
                "remaining_seconds": remaining,
                "completed": completed,
                "score": score,
                "progress_pct": progress_pct,
                "progress_bar": progress_bar,
                "progress_text": progress_text
            }
    return {"team_logged_in": False}

# -----------------------------
# LANDING & REGISTRATION
# -----------------------------
@app.route("/")
def index():
    if "visited_loading" not in session:
        session["visited_loading"] = True
        return render_template("loading.html")
    return redirect(url_for("home_page"))

@app.route("/home")
def home_page():
    if "team_id" in session:
        team = get_team_by_id(session["team_id"])
        if team:
            completed = team.get("completed")
            current_level = team.get("current_level", 1)
            
            if get_remaining_seconds(team) <= 0 and not completed:
                return redirect(url_for("mission_failed"))
                
            if completed:
                return redirect(url_for("congrats"))
            
            if current_level == 1:
                return redirect(url_for("level1"))
            
            # Verify if QR code scanned progress exists
            has_scanned = False
            if use_mock:
                has_scanned = any(p["team_id"] == session["team_id"] and p["qr_id"] == current_level for p in mock_progress)
            else:
                qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", current_level).execute()
                has_scanned = bool(qr_check.data)

            if has_scanned:
                return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
            else:
                return redirect(url_for("success", level_id=current_level-1))
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    global mock_team_id_seq
    team_name = request.form["team_name"].strip()
    leader_name = request.form["leader_name"].strip()
    phone = request.form["phone"].strip()

    if use_mock:
        # Check if already exists in mock
        for t in mock_teams.values():
            if t["team_name"].lower() == team_name.lower():
                session["team_id"] = t["id"]
                return redirect(url_for("home_page"))
        
        # Create mock team
        t_id = mock_team_id_seq
        mock_team_id_seq += 1
        mock_teams[t_id] = {
            "id": t_id,
            "team_name": team_name,
            "leader_name": leader_name,
            "phone": phone,
            "current_level": 1,
            "start_time": datetime.now(timezone.utc),
            "completion_time": None,
            "completed": False,
            "winner_status": False,
            "score": 0
        }
        session["team_id"] = t_id
        mock_progress.append({"team_id": t_id, "qr_id": 1})
        return redirect(url_for("level1"))

    try:
        chk = supabase.table("teams").select("*").eq("team_name", team_name).execute()
        if chk.data:
            session["team_id"] = chk.data[0]["id"]
            return redirect(url_for("home_page"))
            
        now_str = datetime.now(timezone.utc).isoformat()
        insert_response = supabase.table("teams").insert({
            "team_name": team_name,
            "leader_name": leader_name,
            "phone": phone,
            "current_level": 1,
            "start_time": now_str,
            "score": 0,
            "completed": False,
            "winner_status": False
        }).execute()
        
        if insert_response.data:
            team_id = insert_response.data[0]["id"]
            session["team_id"] = team_id
            
            supabase.table("progress").insert({
                "team_id": team_id,
                "qr_id": 1
            }).execute()
            
            return redirect(url_for("level1"))
    except Exception as e:
        print(f"Error registering team: {e}")
        
    return redirect(url_for("home_page"))

# -----------------------------
# QR VERIFICATION ROUTE
# -----------------------------
@app.route("/qr/<int:qr_id>")
def qr_scan(qr_id):
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team:
        return redirect(url_for("logout"))
    
    if get_remaining_seconds(team) <= 0 and not team.get("completed"):
        return redirect(url_for("mission_failed"))
        
    current_level = team.get("current_level", 1)
    completed = team.get("completed", False)
    
    if completed:
        return redirect(url_for("congrats"))

    if qr_id == current_level:
        if use_mock:
            if not any(p["team_id"] == session["team_id"] and p["qr_id"] == qr_id for p in mock_progress):
                mock_progress.append({"team_id": session["team_id"], "qr_id": qr_id})
        else:
            try:
                supabase.table("progress").insert({
                    "team_id": session["team_id"],
                    "qr_id": qr_id
                }).execute()
            except:
                pass
            
        if qr_id == 5:
            return redirect(url_for("final"))
        else:
            return redirect(url_for(f"level{qr_id}"))
            
    elif qr_id < current_level:
        return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
    else:
        return redirect(url_for("success", level_id=current_level-1))

# -----------------------------
# MISSION SUCCESS SCREEN
# -----------------------------
@app.route("/success/<int:level_id>")
def success(level_id):
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team:
        return redirect(url_for("logout"))
        
    if get_remaining_seconds(team) <= 0 and not team.get("completed"):
        return redirect(url_for("mission_failed"))
    
    current_level = team.get("current_level", 1)
    completed = team.get("completed", False)
    
    if completed:
        return redirect(url_for("congrats"))
    
    if level_id >= current_level:
        return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
    
    locations = {
        1: {"loc": "Library", "qr": 2, "reward": "LI"},
        2: {"loc": "Seminar Hall", "qr": 3, "reward": "BR"},
        3: {"loc": "Block C", "qr": 4, "reward": "AR"},
        4: {"loc": "Master Server Room", "qr": 5, "reward": "Y"}
    }
    
    info = locations.get(level_id, {"loc": "Next Mission Area", "qr": level_id+1, "reward": "Fragment"})
    
    return render_template(
        "success.html",
        level_id=level_id,
        next_loc=info["loc"],
        next_qr=info["qr"],
        reward=info["reward"]
    )


# -----------------------------
# DUAL MODE EMERGENCY BYPASS VERIFICATION
# -----------------------------
@app.route("/verify_bypass", methods=["POST"])
def verify_bypass():
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team:
        return redirect(url_for("logout"))
        
    if get_remaining_seconds(team) <= 0 and not team.get("completed"):
        return redirect(url_for("mission_failed"))

    qr_id = int(request.form.get("qr_id", 0))
    bypass_key = request.form.get("bypass_key", "").strip().upper()

    # Secret bypass passcodes matches: QR-ID -> PASSCODE
    bypass_keys = {
        2: "BYPASS_LIB_2",
        3: "BYPASS_SEM_3",
        4: "BYPASS_BLK_4",
        5: "BYPASS_MST_5"
    }

    correct_key = bypass_keys.get(qr_id)

    if correct_key and bypass_key == correct_key:
        # Route logic behaves exactly like a successful physical QR code scan
        return redirect(url_for("qr_scan", qr_id=qr_id))
    else:
        # Re-render the checkpoint screen but pass along invalid key credentials error message
        level_id = qr_id - 1
        locations = {
            1: {"loc": "Library", "qr": 2, "reward": "LI"},
            2: {"loc": "Seminar Hall", "qr": 3, "reward": "BR"},
            3: {"loc": "Block C", "qr": 4, "reward": "AR"},
            4: {"loc": "Master Server Room", "qr": 5, "reward": "Y"}
        }
        info = locations.get(level_id, {"loc": "Next Mission Area", "qr": qr_id, "reward": "Fragment"})
        return render_template(
            "success.html",
            level_id=level_id,
            next_loc=info["loc"],
            next_qr=qr_id,
            reward=info["reward"],
            error="INVALID OVERRIDE CODE: Signature signature unrecognized."
        )

# -----------------------------

# MISSION LEVELS (1-4)
# -----------------------------
@app.route("/level1", methods=["GET", "POST"])
def level1():
    t_red = verify_session_timer()
    if t_red: return t_red
    
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team: return redirect(url_for("logout"))
    
    current_level = team.get("current_level", 1)
    if team.get("completed"): return redirect(url_for("congrats"))
    
    if current_level != 1:
        has_scanned = False
        if use_mock:
            has_scanned = any(p["team_id"] == session["team_id"] and p["qr_id"] == current_level for p in mock_progress)
        else:
            qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", current_level).execute()
            has_scanned = bool(qr_check.data)

        if has_scanned:
            return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        if answer == "LIBRARY":
            if use_mock:
                mock_teams[session["team_id"]]["current_level"] = 2
                mock_teams[session["team_id"]]["score"] = 100
            else:
                supabase.table("teams").update({
                    "current_level": 2,
                    "score": 100
                }).eq("id", session["team_id"]).execute()
            return redirect(url_for("success", level_id=1))
        else:
            error = "ACCESS DENIED: Decryption Key Invalid"

    return render_template("level1.html", error=error)

@app.route("/level2", methods=["GET", "POST"])
def level2():
    t_red = verify_session_timer()
    if t_red: return t_red
    
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team: return redirect(url_for("logout"))
    
    current_level = team.get("current_level", 1)
    if team.get("completed"): return redirect(url_for("congrats"))
    
    if current_level < 2:
        return redirect(url_for("level1"))
    elif current_level > 2:
        has_scanned = False
        if use_mock:
            has_scanned = any(p["team_id"] == session["team_id"] and p["qr_id"] == current_level for p in mock_progress)
        else:
            qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", current_level).execute()
            has_scanned = bool(qr_check.data)

        if has_scanned:
            return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))
            
    # Check if QR 2 scanned progress exists
    has_scanned_qr = False
    if use_mock:
        has_scanned_qr = any(p["team_id"] == session["team_id"] and p["qr_id"] == 2 for p in mock_progress)
    else:
        qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", 2).execute()
        has_scanned_qr = bool(qr_check.data)

    if not has_scanned_qr:
        return redirect(url_for("success", level_id=1))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip()
        if answer == "125":
            if use_mock:
                mock_teams[session["team_id"]]["current_level"] = 3
                mock_teams[session["team_id"]]["score"] = 200
            else:
                supabase.table("teams").update({
                    "current_level": 3,
                    "score": 200
                }).eq("id", session["team_id"]).execute()
            return redirect(url_for("success", level_id=2))
        else:
            error = "ACCESS DENIED: Compiler output incorrect"

    return render_template("level2.html", error=error)

@app.route("/level3", methods=["GET", "POST"])
def level3():
    t_red = verify_session_timer()
    if t_red: return t_red
    
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team: return redirect(url_for("logout"))
    
    current_level = team.get("current_level", 1)
    if team.get("completed"): return redirect(url_for("congrats"))
    
    if current_level < 3:
        return redirect(url_for(f"level{current_level}"))
    elif current_level > 3:
        has_scanned = False
        if use_mock:
            has_scanned = any(p["team_id"] == session["team_id"] and p["qr_id"] == current_level for p in mock_progress)
        else:
            qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", current_level).execute()
            has_scanned = bool(qr_check.data)

        if has_scanned:
            return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))
            
    has_scanned_qr = False
    if use_mock:
        has_scanned_qr = any(p["team_id"] == session["team_id"] and p["qr_id"] == 3 for p in mock_progress)
    else:
        qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", 3).execute()
        has_scanned_qr = bool(qr_check.data)

    if not has_scanned_qr:
        return redirect(url_for("success", level_id=2))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        if answer == "ALPHA":
            if use_mock:
                mock_teams[session["team_id"]]["current_level"] = 4
                mock_teams[session["team_id"]]["score"] = 300
            else:
                supabase.table("teams").update({
                    "current_level": 4,
                    "score": 300
                }).eq("id", session["team_id"]).execute()
            return redirect(url_for("success", level_id=3))
        else:
            error = "ACCESS DENIED: Clue token unrecognized"

    return render_template("level3.html", error=error)

@app.route("/level4", methods=["GET", "POST"])
def level4():
    t_red = verify_session_timer()
    if t_red: return t_red
    
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team: return redirect(url_for("logout"))
    
    current_level = team.get("current_level", 1)
    if team.get("completed"): return redirect(url_for("congrats"))
    
    if current_level < 4:
        return redirect(url_for(f"level{current_level}"))
    elif current_level > 4:
        has_scanned = False
        if use_mock:
            has_scanned = any(p["team_id"] == session["team_id"] and p["qr_id"] == current_level for p in mock_progress)
        else:
            qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", current_level).execute()
            has_scanned = bool(qr_check.data)

        if has_scanned:
            return redirect(url_for("final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))
            
    has_scanned_qr = False
    if use_mock:
        has_scanned_qr = any(p["team_id"] == session["team_id"] and p["qr_id"] == 4 for p in mock_progress)
    else:
        qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", 4).execute()
        has_scanned_qr = bool(qr_check.data)

    if not has_scanned_qr:
        return redirect(url_for("success", level_id=3))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        if answer == "BETA":
            if use_mock:
                mock_teams[session["team_id"]]["current_level"] = 5
                mock_teams[session["team_id"]]["score"] = 400
            else:
                supabase.table("teams").update({
                    "current_level": 5,
                    "score": 400
                }).eq("id", session["team_id"]).execute()
            return redirect(url_for("success", level_id=4))
        else:
            error = "ACCESS DENIED: Binary bitstream parity error"

    return render_template("level4.html", error=error)

# -----------------------------
# FINAL ACCESS & EXPLOIT
# -----------------------------
@app.route("/final", methods=["GET", "POST"])
def final():
    t_red = verify_session_timer()
    if t_red: return t_red
    
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team: return redirect(url_for("logout"))
    
    current_level = team.get("current_level", 1)
    if team.get("completed"): return redirect(url_for("congrats"))
    
    if current_level < 5:
        return redirect(url_for(f"level{current_level}"))
        
    has_scanned_qr = False
    if use_mock:
        has_scanned_qr = any(p["team_id"] == session["team_id"] and p["qr_id"] == 5 for p in mock_progress)
    else:
        qr_check = supabase.table("progress").select("*").eq("team_id", session["team_id"]).eq("qr_id", 5).execute()
        has_scanned_qr = bool(qr_check.data)

    if not has_scanned_qr:
        return redirect(url_for("success", level_id=4))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        if answer == "LAB5":
            finish_time = datetime.now(timezone.utc)
            finish_time_str = finish_time.isoformat()
            
            # Determine Winner
            winner_status = False
            if use_mock:
                has_winner = any(t["winner_status"] for t in mock_teams.values())
                if not has_winner:
                    winner_status = True
                
                mock_teams[session["team_id"]]["completed"] = True
                mock_teams[session["team_id"]]["completion_time"] = finish_time
                mock_teams[session["team_id"]]["score"] = 500
                mock_teams[session["team_id"]]["winner_status"] = winner_status
            else:
                win_check = supabase.table("teams").select("*").eq("winner_status", True).execute()
                if not win_check.data:
                    winner_status = True

                supabase.table("teams").update({
                    "completed": True,
                    "completion_time": finish_time_str,
                    "score": 500,
                    "winner_status": winner_status
                }).eq("id", session["team_id"]).execute()
            
            return redirect(url_for("congrats"))
        else:
            error = "FATAL ERROR: MASTER DECRYPTION OVERRIDE FAILED"

    return render_template("final.html", error=error)

# -----------------------------
# CONGRATS SCREEN
# -----------------------------
@app.route("/congrats")
def congrats():
    if "team_id" not in session:
        return redirect(url_for("home_page"))
    
    team = get_team_by_id(session["team_id"])
    if not team or not team.get("completed"):
        return redirect(url_for("home_page"))
        
    start_str = team.get("start_time")
    finish_str = team.get("completion_time")
    total_seconds = 0
    try:
        if isinstance(start_str, datetime):
            start_dt = start_str
        else:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        
        if isinstance(finish_str, datetime):
            finish_dt = finish_str
        else:
            finish_dt = datetime.fromisoformat(finish_str.replace("Z", "+00:00"))
            
        total_seconds = int((finish_dt - start_dt).total_seconds())
    except:
        pass
        
    formatted_time = format_seconds(total_seconds)
    
    return render_template("congrats.html", team_name=team.get("team_name"), formatted_time=formatted_time)

# -----------------------------
# TIMEOUT / FAILED SCREEN
# -----------------------------
@app.route("/failed")
def mission_failed():
    return render_template("failed.html")

# -----------------------------
# ADMIN LOGIN & CONTROLS
# -----------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    
    error = ""
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            error = "CREDENTIAL DIAGNOSTICS: Authentication Signature Corrupted"
            
    return render_template("admin_login.html", error=error)

@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    search = request.args.get("search", "").strip()
    status_filter = request.args.get("filter", "all")

    if use_mock:
        total_teams = len(mock_teams)
        completed_teams = sum(1 for t in mock_teams.values() if t["completed"])
        active_teams = total_teams - completed_teams
        winner_team = next((t["team_name"] for t in mock_teams.values() if t["winner_status"]), None)
        teams_data = list(mock_teams.values())
    else:
        try:
            tot_res = supabase.table("teams").select("id", count="exact").execute()
            total_teams = tot_res.count if tot_res.count is not None else 0

            comp_res = supabase.table("teams").select("id", count="exact").eq("completed", True).execute()
            completed_teams = comp_res.count if comp_res.count is not None else 0
            active_teams = total_teams - completed_teams

            win_res = supabase.table("teams").select("team_name").eq("winner_status", True).execute()
            winner_team = win_res.data[0]["team_name"] if win_res.data else None

            query = supabase.table("teams").select("*")
            if status_filter == "completed":
                query = query.eq("completed", True)
            elif status_filter == "active":
                query = query.eq("completed", False)
                
            teams_data = query.execute().data
        except Exception as e:
            print(f"Admin telemetry query failed: {e}")
            total_teams = completed_teams = active_teams = 0
            winner_team = None
            teams_data = []

    processed_teams = []
    for t in teams_data:
        if search:
            s_lower = search.lower()
            if s_lower not in t["team_name"].lower() and s_lower not in t["leader_name"].lower() and s_lower not in t["phone"].lower():
                continue

        rem_sec = get_remaining_seconds(t)
        
        duration = "In Progress"
        if t["completed"]:
            try:
                if isinstance(t["start_time"], datetime):
                    s_dt = t["start_time"]
                else:
                    s_dt = datetime.fromisoformat(t["start_time"].replace("Z", "+00:00"))
                
                if isinstance(t["completion_time"], datetime):
                    f_dt = t["completion_time"]
                else:
                    f_dt = datetime.fromisoformat(t["completion_time"].replace("Z", "+00:00"))
                    
                duration = format_seconds(int((f_dt - s_dt).total_seconds()))
            except:
                duration = "Solved"
        elif rem_sec <= 0:
            duration = "Timed Out"

        start_disp = t["start_time"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(t["start_time"], datetime) else t["start_time"][:19].replace("T", " ")
        finish_disp = "N/A"
        if t["completion_time"]:
            finish_disp = t["completion_time"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(t["completion_time"], datetime) else t["completion_time"][:19].replace("T", " ")

        processed_teams.append({
            "id": t["id"],
            "team_name": t["team_name"],
            "leader_name": t["leader_name"],
            "phone": t["phone"],
            "current_level": t["current_level"],
            "score": t["score"],
            "start_time": start_disp,
            "finish_time": finish_disp,
            "completed": 1 if t["completed"] else 0,
            "winner_status": t["winner_status"],
            "remaining_seconds": rem_sec,
            "remaining_time_formatted": f"{rem_sec // 60:02d}:{rem_sec % 60:02d}",
            "formatted_time": duration
        })

    processed_teams.sort(key=lambda x: x["id"], reverse=True)

    return render_template(
        "admin.html",
        teams=processed_teams,
        total_teams=total_teams,
        completed_teams=completed_teams,
        active_teams=active_teams,
        winner_team=winner_team,
        search=search,
        filter=status_filter
    )

@app.route("/admin/export")
def admin_export():
    if not session.get("admin_logged_in"):
        return "Access Denied", 403

    if use_mock:
        teams_data = list(mock_teams.values())
    else:
        try:
            teams_data = supabase.table("teams").select("*").order("id", desc=False).execute().data
        except Exception as e:
            return f"Export Error: {e}", 500
        
    dest = io.StringIO()
    writer = csv.writer(dest)
    writer.writerow([
        "ID", "Team Name", "Leader Name", "Phone Number", 
        "Current Level", "Start Time", "Completion Time", 
        "Completed Status", "Winner Status", "Score"
    ])
    
    for t in teams_data:
        completed_text = "SUCCESS" if t["completed"] else "ACTIVE"
        start_val = t["start_time"].isoformat() if isinstance(t["start_time"], datetime) else t["start_time"]
        finish_val = t["completion_time"].isoformat() if isinstance(t["completion_time"], datetime) else (t["completion_time"] if t["completion_time"] else "N/A")
        writer.writerow([
            t["id"], t["team_name"], t["leader_name"], t["phone"],
            t["current_level"], start_val, finish_val,
            completed_text, "YES" if t["winner_status"] else "NO", t["score"]
        ])

    output = make_response(dest.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=hack_the_campus_teams.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home_page"))

if __name__ == "__main__":
    app.run(debug=True)