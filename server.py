# ============================================================
#  server.py  |  Local API bridge for PM Command Center
#  Connects the dashboard HTML to PMCommandCenter.accdb
#
#  SETUP (run once in Command Prompt):
#    pip install flask flask-cors pyodbc
#
#  START:
#    Double-click start.bat  OR  run: python server.py
#    Then open pm_dashboard.html in your browser
# ============================================================

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pyodbc
import traceback
import os

app = Flask(__name__)
CORS(app)

# ── Serve the dashboard HTML directly ──────────────────────────
# Open http://localhost:5000 in your browser instead of the file directly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route("/api/health", methods=["GET"])
def health():
    try:
        conn = get_connection()
        conn.close()
        return jsonify({"status": "ok", "database": "connected", "path": DB_PATH})
    except Exception as e:
        return jsonify({"status": "error", "database": "unreachable", "error": str(e)}), 500


# ============================================================
#  TABLES (discovery helper)
# ============================================================

@app.route("/api/tables", methods=["GET"])
def get_tables():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        tables = [row.table_name for row in cursor.tables(tableType="TABLE")]
        conn.close()
        return jsonify({"tables": tables})
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


# ============================================================
#  PROJECTS
#  Table  : Projects
#  Key    : ProjectID
#  Columns: ProjectID, UpdatedDate, IsActive, ProjectName,
#           OnDashboard, CapOM, StartDate, EndDate,
#           StatusNotes, Status, BudgetEst,
#           ProjectDescription, ActionItems, FilePath
# ============================================================

@app.route("/api/projects", methods=["GET"])
def get_projects():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM [Projects]")
        projects = rows_to_dicts(cursor)
        conn.close()
        result = []
        for p in projects:
            try:
                p["project"]      = p.get("ProjectName", "")
                p["status"]       = p.get("Status", "")
                p["active"]       = bool(p.get("IsActive", False))
                p["dashboard"]    = p.get("OnDashboard", "Y")
                p["capOM"]        = p.get("CapOM", "")
                p["startDate"]    = str(p.get("StartDate", "") or "")
                p["endDate"]      = str(p.get("EndDate", "") or "")
                p["statusNotes"]  = p.get("StatusNotes", "") or ""
                p["budget"]       = float(p.get("BudgetEst") or 0)
                p["justification"]= p.get("ProjectDescription", "") or ""
                p["notes"]        = p.get("ActionItems", "") or ""
                p["id"]           = p.get("ProjectID")
                p["location"]     = p.get("Location", "") or ""
                p["progress"]     = int(p.get("Progress") or 0) if p.get("Progress") is not None else 0
                p["spent"]        = float(p.get("Spent") or 0) if p.get("Spent") is not None else 0.0
                p["updated"]      = str(p.get("UpdatedDate", "") or "")
                result.append(p)
            except Exception as row_err:
                print(f"Skipping project row {p.get('ProjectID')}: {row_err}", flush=True)
        print(f"Returning {len(result)} of {len(projects)} projects", flush=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/projects/<int:project_id>", methods=["PATCH"])
def update_project(project_id):
    try:
        data = request.get_json()
        print(f"PATCH /api/projects/{project_id} data: {data}", flush=True)
        if not data:
            return jsonify({"error": "No data provided"}), 400
        # Map dashboard field names back to Access column names
        field_map = {
            "project":      "ProjectName",
            "status":       "Status",
            "active":       "IsActive",
            "dashboard":    "OnDashboard",
            "capOM":        "CapOM",
            "startDate":    "StartDate",
            "endDate":      "EndDate",
            "statusNotes":  "StatusNotes",
            "budget":       "BudgetEst",
            "justification":"ProjectDescription",
            "notes":        "ActionItems",
            "location":     "Location",
            "progress":     "Progress",
            "spent":        "Spent",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        # Convert empty date strings to None for Access
        for date_field in ["StartDate", "EndDate"]:
            if date_field in mapped and mapped[date_field] in ("", "TBD"):
                mapped[date_field] = None
        # Convert empty strings to None for Access Memo/Text fields
        for field in ["StatusNotes", "ProjectDescription", "ActionItems", "Location"]:
            if field in mapped and mapped[field] == "":
                mapped[field] = None
        if "IsActive" in mapped:
            mapped["IsActive"] = bool(mapped["IsActive"])
        if "BudgetEst" in mapped:
            mapped["BudgetEst"] = float(mapped["BudgetEst"]) if mapped["BudgetEst"] not in (None, "", "TBD") else None
        if "Progress" in mapped:
            mapped["Progress"] = int(mapped["Progress"]) if mapped["Progress"] not in (None, "") else 0
        if "Spent" in mapped:
            mapped["Spent"] = float(mapped["Spent"]) if mapped["Spent"] not in (None, "") else 0.0
        if not mapped:
            return jsonify({"error": "No recognised fields to update"}), 400
        conn = get_connection()
        cursor = conn.cursor()
        fields = ", ".join(f"[{k}] = ?" for k in mapped.keys())
        values = list(mapped.values()) + [project_id]
        cursor.execute(f"UPDATE [Projects] SET {fields} WHERE [ProjectID] = ?", values)
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        import sys
        print(f"UPDATE PROJECT {project_id} FAILED: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        sys.stdout.flush()
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/projects", methods=["POST"])
def create_project():
    try:
        data = request.get_json()
        print(f"POST /api/projects data: {data}", flush=True)
        field_map = {
            "project":      "ProjectName",
            "status":       "Status",
            "active":       "IsActive",
            "dashboard":    "OnDashboard",
            "capOM":        "CapOM",
            "startDate":    "StartDate",
            "endDate":      "EndDate",
            "statusNotes":  "StatusNotes",
            "budget":       "BudgetEst",
            "justification":"ProjectDescription",
            "notes":        "ActionItems",
            "location":     "Location",
            "progress":     "Progress",
            "spent":        "Spent",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        # Convert empty strings to None for Access memo/text fields
        for k in list(mapped.keys()):
            if mapped[k] == "":
                mapped[k] = None
        # Convert empty/TBD dates to None
        for date_field in ["StartDate","EndDate"]:
            if date_field in mapped and mapped[date_field] in ("","TBD"):
                mapped[date_field] = None
        conn = get_connection()
        cursor = conn.cursor()
        cols = ", ".join(f"[{k}]" for k in mapped.keys())
        placeholders = ", ".join("?" for _ in mapped)
        cursor.execute(
            f"INSERT INTO [Projects] ({cols}) VALUES ({placeholders})",
            list(mapped.values())
        )
        conn.commit()
        # Get the new AutoNumber ID
        cursor2 = conn.cursor()
        cursor2.execute("SELECT MAX([ProjectID]) FROM [Projects]")
        new_id = cursor2.fetchone()[0]
        conn.close()
        return jsonify({"success": True, "id": new_id}), 201
    except Exception as e:
        print(f"create_project error: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


# ============================================================
#  TASKS
#  Table  : Tasks
#  Key    : TaskID
#  Columns: TaskID, TaskName, ProjectName, Assignee,
#           Priority, Status, DueDate
# ============================================================

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    try:
        project = request.args.get("project")
        conn = get_connection()
        cursor = conn.cursor()
        if project:
            cursor.execute(
                "SELECT * FROM [Tasks] WHERE [ProjectName] = ? ORDER BY [TaskID]",
                [project]
            )
        else:
            cursor.execute("SELECT * FROM [Tasks] ORDER BY [TaskID]")
        tasks = rows_to_dicts(cursor)
        conn.close()
        for t in tasks:
            t["task"]     = t.get("TaskName", "")
            t["project"]  = t.get("ProjectName", "")
            t["assignee"] = t.get("Assignee", "")
            t["priority"] = t.get("Priority", "Medium")
            t["status"]   = t.get("Status", "todo")
            t["due"]      = str(t.get("DueDate", "") or "")
            t["id"]       = t.get("TaskID")
            t["closedDate"] = str(t.get("ClosedDate", "") or "")
        return jsonify(tasks)
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def update_task(task_id):
    try:
        # Reject timestamp IDs — these are new tasks that should be POSTed
        if task_id > 2147483647:
            return jsonify({"error": "Invalid task ID — use POST to create new tasks"}), 400
        data = request.get_json()
        field_map = {
            "task":     "TaskName",
            "project":  "ProjectName",
            "assignee": "Assignee",
            "priority": "Priority",
            "status":   "Status",
            "due":      "DueDate",
            "closedDate": "ClosedDate",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        # Auto-set ClosedDate when status changes to done
        if mapped.get("Status") == "done" and "ClosedDate" not in mapped:
            from datetime import date
            mapped["ClosedDate"] = date.today().isoformat()
        # Clear ClosedDate if task is reopened
        if mapped.get("Status") and mapped["Status"] != "done":
            mapped["ClosedDate"] = None
        # Access date fields can't accept empty strings — convert to None
        if "DueDate" in mapped and mapped["DueDate"] == "":
            mapped["DueDate"] = None
        if "ClosedDate" in mapped and mapped["ClosedDate"] == "":
            mapped["ClosedDate"] = None
        conn = get_connection()
        cursor = conn.cursor()
        fields = ", ".join(f"[{k}] = ?" for k in mapped.keys())
        values = list(mapped.values()) + [task_id]
        cursor.execute(f"UPDATE [Tasks] SET {fields} WHERE [TaskID] = ?", values)
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"update_task error: {e}")
        print(traceback.format_exc())
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500

@app.route("/api/tasks", methods=["POST"])
def create_task():
    try:
        data = request.get_json()
        field_map = {
            "task":     "TaskName",
            "project":  "ProjectName",
            "assignee": "Assignee",
            "priority": "Priority",
            "status":   "Status",
            "due":      "DueDate",
            "closedDate": "ClosedDate",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        # Auto-set ClosedDate if created with done status
        if mapped.get("Status") == "done":
            from datetime import date
            mapped.setdefault("ClosedDate", date.today().isoformat())
        for df in ["DueDate","ClosedDate"]:
            if df in mapped and mapped[df] == "":
                mapped[df] = None
        conn = get_connection()
        cursor = conn.cursor()
        cols = ", ".join(f"[{k}]" for k in mapped.keys())
        placeholders = ", ".join("?" for _ in mapped)
        cursor.execute(
            f"INSERT INTO [Tasks] ({cols}) VALUES ({placeholders})",
            list(mapped.values())
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True}), 201
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


# ============================================================
#  TEAM
#  Table  : Team
#  Key    : TeamMemberID
#  Columns: TeamMemberID, FullName, Role, Department,
#           Email, ActiveTasks, CompletedTasks,
#           CompletionRate, WorkloadPct, Notes
# ============================================================

@app.route("/api/team", methods=["GET"])
def get_team():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM [Team] ORDER BY [FullName]")
        team = rows_to_dicts(cursor)
        conn.close()
        for m in team:
            m["name"]        = m.get("FullName", "")
            m["role"]        = m.get("Role", "")
            m["dept"]        = m.get("Department", "")
            m["email"]       = m.get("Email", "")
            m["activeTasks"] = m.get("ActiveTasks", 0)
            m["completed"]   = m.get("CompletedTasks", 0)
            m["rate"]        = m.get("CompletionRate", 0)
            m["load"]        = m.get("WorkloadPct", 0)
            m["notes"]       = m.get("Notes", "") or ""
            m["id"]          = m.get("TeamMemberID")
            m["shortName"]   = m.get("ShortName", "") or ""
        return jsonify(team)
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/team/<int:member_id>", methods=["PATCH"])
def update_team_member(member_id):
    try:
        data = request.get_json()
        field_map = {
            "name":        "FullName",
            "shortName":   "ShortName",
            "role":        "Role",
            "dept":        "Department",
            "email":       "Email",
            "activeTasks": "ActiveTasks",
            "completed":   "CompletedTasks",
            "rate":        "CompletionRate",
            "load":        "WorkloadPct",
            "notes":       "Notes",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        conn = get_connection()
        cursor = conn.cursor()
        fields = ", ".join(f"[{k}] = ?" for k in mapped.keys())
        values = list(mapped.values()) + [member_id]
        cursor.execute(f"UPDATE [Team] SET {fields} WHERE [TeamMemberID] = ?", values)
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/team", methods=["POST"])
def create_team_member():
    try:
        data = request.get_json()
        field_map = {
            "name":        "FullName",
            "shortName":   "ShortName",
            "role":        "Role",
            "dept":        "Department",
            "email":       "Email",
            "activeTasks": "ActiveTasks",
            "completed":   "CompletedTasks",
            "rate":        "CompletionRate",
            "load":        "WorkloadPct",
            "notes":       "Notes",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        # Convert empty strings to correct types for Access
        for num_field in ["ActiveTasks","CompletedTasks"]:
            if num_field in mapped:
                mapped[num_field] = int(mapped[num_field]) if mapped[num_field] not in (None,"") else 0
        for float_field in ["CompletionRate","WorkloadPct"]:
            if float_field in mapped:
                mapped[float_field] = float(mapped[float_field]) if mapped[float_field] not in (None,"") else 0.0
        for text_field in ["Notes","Email","ShortName"]:
            if text_field in mapped and mapped[text_field] == "":
                mapped[text_field] = None
        conn = get_connection()
        cursor = conn.cursor()
        cols = ", ".join(f"[{k}]" for k in mapped.keys())
        placeholders = ", ".join("?" for _ in mapped)
        cursor.execute(
            f"INSERT INTO [Team] ({cols}) VALUES ({placeholders})",
            list(mapped.values())
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True}), 201
    except Exception as e:
        print(f"create_team_member error: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500



# ============================================================
#  EOC
#  Table  : EOC
#  Key    : EOCID
# ============================================================

@app.route("/api/eoc", methods=["GET"])
def get_eoc():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM [EOC]")
        rows = rows_to_dicts(cursor)
        conn.close()
        for r in rows:
            r["id"]                  = r.get("EOCID")
            r["task"]                = r.get("TaskName", "") or ""
            r["whoAlertGoesTo"]      = r.get("WhoAlertGoesTo", "") or ""
            r["changeToWhat"]        = r.get("ChangeToWhat", "") or ""
            r["idRunningUnder"]      = r.get("RunningUnderID", "") or ""
            r["changeToServiceAcct"] = r.get("ChangeToServiceAcct", "") or ""
            r["assignedSME"]         = r.get("AssignedSME", "") or ""
            r["srNumber"]            = r.get("SRNumber", "") or ""
            r["startDate"]           = str(r.get("StartDate", "") or "")
            r["originalEndDate"]     = str(r.get("OriginalEndDate", "") or "")
            r["revisedEndDate"]      = str(r.get("RevisedEndDate", "") or "")
            r["pctComplete"]         = r.get("PctComplete", "0%") or "0%"
            r["daysRemaining"]       = r.get("DaysRemaining", "N/A") or "N/A"
            r["status"]              = r.get("Status", "Not Started") or "Not Started"
            r["notes"]               = r.get("Notes", "") or ""
            r["eoc"]                 = r.get("EOC", "") or ""
        return jsonify(rows)
    except Exception as e:
        print(f"get_eoc error: {e}", flush=True)
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/eoc/<int:eoc_id>", methods=["PATCH"])
def update_eoc(eoc_id):
    try:
        data = request.get_json()
        print(f"PATCH /api/eoc/{eoc_id} data: {data}", flush=True)
        if not data:
            return jsonify({"error": "No data provided"}), 400
        field_map = {
            "task":                "TaskName",
            "whoAlertGoesTo":      "WhoAlertGoesTo",
            "changeToWhat":        "ChangeToWhat",
            "idRunningUnder":      "RunningUnderID",
            "changeToServiceAcct": "ChangeToServiceAcct",
            "assignedSME":         "AssignedSME",
            "srNumber":            "SRNumber",
            "startDate":           "StartDate",
            "originalEndDate":     "OriginalEndDate",
            "revisedEndDate":      "RevisedEndDate",
            "pctComplete":         "PctComplete",
            "daysRemaining":       "DaysRemaining",
            "status":              "Status",
            "notes":               "Notes",
            "eoc":                 "EOC",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        for date_field in ["StartDate","OriginalEndDate","RevisedEndDate"]:
            if date_field in mapped and mapped[date_field] in ("","TBD"):
                mapped[date_field] = None
        # Convert all empty strings to None for Access text/memo fields
        for k in list(mapped.keys()):
            if mapped[k] == "":
                mapped[k] = None
        conn = get_connection()
        cursor = conn.cursor()
        fields = ", ".join(f"[{k}] = ?" for k in mapped.keys())
        values = list(mapped.values()) + [eoc_id]
        cursor.execute(f"UPDATE [EOC] SET {fields} WHERE [EOCID] = ?", values)
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"update_eoc error: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/eoc", methods=["POST"])
def create_eoc():
    try:
        data = request.get_json()
        field_map = {
            "task":                "TaskName",
            "whoAlertGoesTo":      "WhoAlertGoesTo",
            "changeToWhat":        "ChangeToWhat",
            "idRunningUnder":      "RunningUnderID",
            "changeToServiceAcct": "ChangeToServiceAcct",
            "assignedSME":         "AssignedSME",
            "srNumber":            "SRNumber",
            "startDate":           "StartDate",
            "originalEndDate":     "OriginalEndDate",
            "revisedEndDate":      "RevisedEndDate",
            "pctComplete":         "PctComplete",
            "daysRemaining":       "DaysRemaining",
            "status":              "Status",
            "notes":               "Notes",
            "eoc":                 "EOC",
        }
        mapped = {field_map[k]: v for k, v in data.items() if k in field_map}
        for date_field in ["StartDate","OriginalEndDate","RevisedEndDate"]:
            if date_field in mapped and mapped[date_field] in ("","TBD"):
                mapped[date_field] = None
        # Convert all empty strings to None for Access
        for k in list(mapped.keys()):
            if mapped[k] == "":
                mapped[k] = None
        conn = get_connection()
        cursor = conn.cursor()
        cols = ", ".join(f"[{k}]" for k in mapped.keys())
        placeholders = ", ".join("?" for _ in mapped)
        cursor.execute(f"INSERT INTO [EOC] ({cols}) VALUES ({placeholders})", list(mapped.values()))
        conn.commit()
        conn.close()
        return jsonify({"success": True}), 201
    except Exception as e:
        print(f"create_eoc error: {e}", flush=True)
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/eoc/<int:eoc_id>", methods=["DELETE"])
def delete_eoc(eoc_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [EOC] WHERE [EOCID] = ?", [eoc_id])
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
#  STATIC FILE SERVING
# ============================================================

@app.route("/")
def serve_dashboard():
    """Serve the dashboard HTML."""
    for fname in sorted(os.listdir(BASE_DIR)):
        if fname.lower().startswith("pm_dashboard") and fname.lower().endswith(".html"):
            return send_from_directory(BASE_DIR, fname)
    return "pm_dashboard HTML file not found in this folder", 404

@app.route("/<path:filename>")
def serve_static(filename):
    """Serve static files — never intercept API routes."""
    if filename.startswith("api"):
        from flask import abort
        abort(404)
    return send_from_directory(BASE_DIR, filename)

# ============================================================
#  CONFIGURATION
# ============================================================

DB_PATH = os.path.join(BASE_DIR, "PMCommandCenter.accdb")

def get_connection():
    conn_str = (
        r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={DB_PATH};"
    )
    return pyodbc.connect(conn_str)

def rows_to_dicts(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ============================================================
#  HEALTH CHECK
# ============================================================


# ============================================================
#  START
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  PM Command Center — Local API Server")
    print("=" * 55)
    print(f"  Database : {DB_PATH}")
    print(f"  Health   : http://localhost:5000/api/health")
    print(f"  Tables   : http://localhost:5000/api/tables")
    print(f"  Projects : http://localhost:5000/api/projects")
    print(f"  Tasks    : http://localhost:5000/api/tasks")
    print(f"  Team     : http://localhost:5000/api/team")
    print("=" * 55)
    print()
    print("  >>> OPEN THIS URL IN YOUR BROWSER <<<")
    print("  >>> http://localhost:5000           <<<")
    print()
    print("  DO NOT open the HTML file directly.")
    print("  Press Ctrl+C to stop.")
    print()
    app.run(host="127.0.0.1", port=5000, debug=True)
