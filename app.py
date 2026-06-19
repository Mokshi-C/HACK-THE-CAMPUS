from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3
from datetime import datetime
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "hack_the_campus_secret_secure_key"

import os

# Use /tmp/database.db in Vercel serverless functions (writeable folder)
if os.environ.get("VERCEL"):
    DB_NAME = "/tmp/database.db"
else:
    DB_NAME = "database.db"

# Admin credentials generated dynamically on boot
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("cyberadmin2026")

# -----------------------------
# DATABASE INITIALIZATION
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # In Vercel, the app restarts frequently. Do not drop table, just create if not exists.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS teams(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT NOT NULL,
        leader_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        current_level INTEGER DEFAULT 1,
        start_time TEXT,
        finish_time TEXT,
        total_time INTEGER DEFAULT NULL,
        completed INTEGER DEFAULT 0,
        score INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

init_db()

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def get_team_status(team_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT current_level, completed, start_time, score FROM teams WHERE id = ?", (team_id,))
    res = cur.fetchone()
    conn.close()
    return res

def format_seconds(seconds):
    if seconds is None:
        return "N/A"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{int(minutes)} Minutes {int(secs)} Seconds"

# Context processor to inject active team details into templates automatically
@app.context_processor
def inject_team_info():
    if "team_id" in session:
        status = get_team_status(session["team_id"])
        if status:
            current_level, completed, start_time_str, score = status
            try:
                dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
                start_time_epoch = int(dt.timestamp())
            except Exception:
                start_time_epoch = 0

            # Compute progress
            if completed == 1:
                progress_pct = 100
                progress_bar = "██████████"
                progress_text = "COMPLETED"
            else:
                progress_pct = (current_level - 1) * 20
                if current_level == 5:
                    progress_pct = 90
                
                filled = int(progress_pct / 10)
                empty = 10 - filled
                progress_bar = "█" * filled + "░" * empty
                if current_level == 5:
                    progress_text = "FINAL MISSION"
                else:
                    progress_text = f"MISSION {current_level} OF 5"

            return {
                "team_logged_in": True,
                "team_name": session.get("team_name"),
                "leader_name": session.get("leader_name"),
                "current_level": current_level,
                "start_time_epoch": start_time_epoch,
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
def home():
    if "team_id" in session:
        status = get_team_status(session["team_id"])
        if status:
            current_level, completed, _, _ = status
            if completed == 1:
                return redirect(url_for("congrats"))
            # Redirect to their active level page or success screen
            if session.get("qr_scanned") == current_level or current_level == 1:
                return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
            else:
                return redirect(url_for("success", level_id=current_level-1))
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    team_name = request.form["team_name"].strip()
    leader_name = request.form["leader_name"].strip()
    phone = request.form["phone"].strip()

    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO teams (team_name, leader_name, phone, current_level, start_time, score)
    VALUES (?, ?, ?, 1, ?, 0)
    """, (team_name, leader_name, phone, start_time))
    team_id = cur.lastrowid
    conn.commit()
    conn.close()

    session["team_id"] = team_id
    session["team_name"] = team_name
    session["leader_name"] = leader_name
    session["qr_scanned"] = 1 # Level 1 doesn't require QR scan to start

    return redirect(url_for("level1"))

# -----------------------------
# QR VERIFICATION ROUTE
# -----------------------------
@app.route("/qr/<int:qr_id>")
def qr_scan(qr_id):
    if "team_id" not in session:
        # Save scanned QR in session for temporary use upon registration
        session["pending_qr"] = qr_id
        return redirect(url_for("home"))
    
    status = get_team_status(session["team_id"])
    if not status:
        return redirect(url_for("logout"))
    
    current_level, completed, _, _ = status
    if completed == 1:
        return redirect(url_for("congrats"))

    # Verify if they are scanning the correct QR code for their current level
    if qr_id == current_level:
        session["qr_scanned"] = qr_id
        if qr_id == 5:
            return redirect(url_for("final"))
        else:
            return redirect(url_for(f"level{qr_id}"))
    elif qr_id < current_level:
        # Already solved this level, let's redirect them to where they should be
        session["qr_scanned"] = current_level
        return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
    else:
        # Trying to scan a future level QR prematurely
        return redirect(url_for("success", level_id=current_level-1))

# -----------------------------
# MISSION SUCCESS SCREEN
# -----------------------------
@app.route("/success/<int:level_id>")
def success(level_id):
    if "team_id" not in session:
        return redirect(url_for("home"))
    
    status = get_team_status(session["team_id"])
    if not status:
        return redirect(url_for("logout"))
    
    current_level, completed, _, _ = status
    if completed == 1:
        return redirect(url_for("congrats"))
    
    # Ensure they can only view success of a level they actually completed
    if level_id >= current_level:
        return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
    
    # Map next coordinates based on completed level
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
# LEVEL 1
# -----------------------------
@app.route("/level1", methods=["GET", "POST"])
def level1():
    if "team_id" not in session:
        return redirect(url_for("home"))
    
    status = get_team_status(session["team_id"])
    if not status:
        return redirect(url_for("logout"))
    
    current_level, completed, _, _ = status
    if completed == 1:
        return redirect(url_for("congrats"))
    
    if current_level != 1:
        if session.get("qr_scanned") == current_level:
            return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        if answer == "LIBRARY":
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("UPDATE teams SET current_level = 2, score = 100 WHERE id = ?", (session["team_id"],))
            conn.commit()
            conn.close()
            return redirect(url_for("success", level_id=1))
        else:
            error = "ACCESS DENIED: Decryption Key Invalid"

    return render_template("level1.html", error=error)

# -----------------------------
# LEVEL 2
# -----------------------------
@app.route("/level2", methods=["GET", "POST"])
def level2():
    if "team_id" not in session:
        return redirect(url_for("home"))
    
    status = get_team_status(session["team_id"])
    if not status:
        return redirect(url_for("logout"))
    
    current_level, completed, _, _ = status
    if completed == 1:
        return redirect(url_for("congrats"))
    
    if current_level < 2:
        return redirect(url_for("level1"))
    elif current_level > 2:
        if session.get("qr_scanned") == current_level:
            return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))
            
    if session.get("qr_scanned") != 2:
        return redirect(url_for("success", level_id=1))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip()
        if answer == "125":
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("UPDATE teams SET current_level = 3, score = 200 WHERE id = ?", (session["team_id"],))
            conn.commit()
            conn.close()
            return redirect(url_for("success", level_id=2))
        else:
            error = "ACCESS DENIED: Compiler output incorrect"

    return render_template("level2.html", error=error)

# -----------------------------
# LEVEL 3
# -----------------------------
@app.route("/level3", methods=["GET", "POST"])
def level3():
    if "team_id" not in session:
        return redirect(url_for("home"))
    
    status = get_team_status(session["team_id"])
    if not status:
        return redirect(url_for("logout"))
    
    current_level, completed, _, _ = status
    if completed == 1:
        return redirect(url_for("congrats"))
    
    if current_level < 3:
        return redirect(url_for(f"level{current_level}"))
    elif current_level > 3:
        if session.get("qr_scanned") == current_level:
            return redirect(url_for(f"level{current_level}" if current_level < 5 else "final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))
            
    if session.get("qr_scanned") != 3:
        return redirect(url_for("success", level_id=2))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        if answer == "ALPHA":
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("UPDATE teams SET current_level = 4, score = 300 WHERE id = ?", (session["team_id"],))
            conn.commit()
            conn.close()
            return redirect(url_for("success", level_id=3))
        else:
            error = "ACCESS DENIED: Clue token unrecognized"

    return render_template("level3.html", error=error)

# -----------------------------
# LEVEL 4
# -----------------------------
@app.route("/level4", methods=["GET", "POST"])
def level4():
    if "team_id" not in session:
        return redirect(url_for("home"))
    
    status = get_team_status(session["team_id"])
    if not status:
        return redirect(url_for("logout"))
    
    current_level, completed, _, _ = status
    if completed == 1:
        return redirect(url_for("congrats"))
    
    if current_level < 4:
        return redirect(url_for(f"level{current_level}"))
    elif current_level > 4:
        if session.get("qr_scanned") == current_level:
            return redirect(url_for("final"))
        else:
            return redirect(url_for("success", level_id=current_level-1))
            
    if session.get("qr_scanned") != 4:
        return redirect(url_for("success", level_id=3))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        if answer == "BETA":
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("UPDATE teams SET current_level = 5, score = 400 WHERE id = ?", (session["team_id"],))
            conn.commit()
            conn.close()
            return redirect(url_for("success", level_id=4))
        else:
            error = "ACCESS DENIED: Binary bitstream parity error"

    return render_template("level4.html", error=error)

# -----------------------------
# FINAL ACCESS
# -----------------------------
@app.route("/final", methods=["GET", "POST"])
def final():
    if "team_id" not in session:
        return redirect(url_for("home"))
    
    status = get_team_status(session["team_id"])
    if not status:
        return redirect(url_for("logout"))
    
    current_level, completed, start_time_str, _ = status
    if completed == 1:
        return redirect(url_for("congrats"))
    
    if current_level < 5:
        return redirect(url_for(f"level{current_level}"))
        
    if session.get("qr_scanned") != 5:
        return redirect(url_for("success", level_id=4))

    error = ""
    if request.method == "POST":
        answer = request.form["answer"].strip().upper()
        # Combine clues fragments: LI + BR + AR + Y = LIBRARY. Wait, final answer is LAB5.
        if answer == "LAB5":
            finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate total time in seconds
            start_dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            finish_dt = datetime.now()
            total_seconds = int((finish_dt - start_dt).total_seconds())

            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("""
            UPDATE teams 
            SET completed = 1, finish_time = ?, total_time = ?, score = 500
            WHERE id = ?
            """, (finish_time, total_seconds, session["team_id"]))
            conn.commit()
            conn.close()
            
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
        return redirect(url_for("home"))
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT team_name, total_time, completed FROM teams WHERE id = ?", (session["team_id"],))
    team = cur.fetchone()
    conn.close()
    
    if not team or team[2] != 1:
        return redirect(url_for("home"))
        
    team_name, total_seconds, _ = team
    formatted_time = format_seconds(total_seconds)
    
    return render_template("congrats.html", team_name=team_name, formatted_time=formatted_time)

# -----------------------------
# LEADERBOARD
# -----------------------------
@app.route("/leaderboard")
def leaderboard():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Sort: Completed teams first (by lowest total_time), then Active teams (by level desc, start time asc)
    cur.execute("""
    SELECT team_name, current_level, completed, total_time, score
    FROM teams
    ORDER BY 
        completed DESC,
        CASE WHEN completed = 1 THEN total_time ELSE 999999999 END ASC,
        current_level DESC,
        start_time ASC
    """)
    teams = cur.fetchall()
    conn.close()

    # Process teams formatting for template
    processed_teams = []
    for team in teams:
        team_name, current_level, completed, total_seconds, score = team
        formatted_time = format_seconds(total_seconds) if completed == 1 else "In Progress"
        status_text = "COMPLETED" if completed == 1 else f"Mission {current_level}"
        processed_teams.append({
            "team_name": team_name,
            "current_level": current_level,
            "completed": completed,
            "formatted_time": formatted_time,
            "score": score,
            "status_text": status_text
        })

    return render_template("leaderboard.html", teams=processed_teams)

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

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Get quick statistics
    cur.execute("SELECT COUNT(*) FROM teams")
    total_teams = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM teams WHERE completed = 1")
    completed_teams = cur.fetchone()[0]

    active_teams = total_teams - completed_teams

    cur.execute("SELECT team_name, total_time FROM teams WHERE completed = 1 ORDER BY total_time ASC LIMIT 1")
    fastest_row = cur.fetchone()
    fastest_team = "N/A"
    if fastest_row:
        fastest_team = f"{fastest_row[0]} ({format_seconds(fastest_row[1])})"

    # Fetch and filter teams
    query = "SELECT id, team_name, leader_name, phone, current_level, start_time, finish_time, total_time, completed, score FROM teams WHERE 1=1"
    params = []
    
    if search:
        query += " AND (team_name LIKE ? OR leader_name LIKE ? OR phone LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        
    if status_filter == "completed":
        query += " AND completed = 1"
    elif status_filter == "active":
        query += " AND completed = 0"
        
    query += " ORDER BY id DESC"
    cur.execute(query, params)
    teams_rows = cur.fetchall()
    conn.close()

    teams = []
    for row in teams_rows:
        teams.append({
            "id": row[0],
            "team_name": row[1],
            "leader_name": row[2],
            "phone": row[3],
            "current_level": row[4],
            "start_time": row[5],
            "finish_time": row[6] if row[6] else "N/A",
            "formatted_time": format_seconds(row[7]) if row[8] == 1 else "In Progress",
            "completed": row[8],
            "score": row[9]
        })

    return render_template(
        "admin.html",
        teams=teams,
        total_teams=total_teams,
        completed_teams=completed_teams,
        active_teams=active_teams,
        fastest_team=fastest_team,
        search=search,
        filter=status_filter
    )

@app.route("/admin/export")
def admin_export():
    if not session.get("admin_logged_in"):
        return "Access Denied", 403

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, team_name, leader_name, phone, current_level, start_time, finish_time, total_time, completed, score FROM teams ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()

    # Generate CSV stream
    dest = io.StringIO()
    writer = csv.writer(dest)
    writer.writerow([
        "ID", "Team Name", "Leader Name", "Phone Number", 
        "Current Level", "Start Time", "Finish Time", 
        "Total Time (Seconds)", "Total Time (Formatted)", "Completed Status", "Score"
    ])
    
    for row in rows:
        formatted_time = format_seconds(row[7]) if row[8] == 1 else "In Progress"
        completed_text = "SUCCESS" if row[8] == 1 else "ACTIVE"
        writer.writerow([
            row[0], row[1], row[2], row[3],
            row[4], row[5], row[6] if row[6] else "N/A",
            row[7] if row[7] else "N/A", formatted_time, completed_text, row[9]
        ])

    output = make_response(dest.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=hack_the_campus_teams.csv"
    output.headers["Content-type"] = "text/csv"
    return output

def make_response(body):
    return Response(body, mimetype="text/csv")

# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)