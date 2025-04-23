from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, text

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.aywynqqvpuspbdbzajmn:Umesh119139143@aws-0-ap-south-1.pooler.supabase.com:6543/postgres'


db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    # Relationship to Tournament
    tournaments = db.relationship('Tournament', backref='owner', lazy=True)


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tournament_type = db.Column(db.String(50), nullable=False)
    num_teams = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(50), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    goals = db.Column(db.Integer, default=0)  # Track goals scored
    team = db.relationship("Team", backref="players")

import json

class Fixture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label=db.Column(db.String(100), nullable=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    winner = db.Column(db.String(100), nullable=True)  # Store winner's name
    goals = db.Column(db.Text, nullable=True)  # Store goals as JSON

    team1 = db.relationship("Team", foreign_keys=[team1_id])
    team2 = db.relationship("Team", foreign_keys=[team2_id])

    def get_goals(self):
        """Retrieve goal data as a Python dictionary."""
        return json.loads(self.goals) if self.goals else {}



class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixture.id'), nullable=False, unique=True)
    team1_score = db.Column(db.Integer, default=0)
    team2_score = db.Column(db.Integer, default=0)
    winning_team = db.Column(db.String(100), nullable=True)  # Store winner name


class PointsTable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    draws = db.Column(db.Integer, default=0)
    goals_scored = db.Column(db.Integer, default=0)
    goals_conceded = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=0)

    team = db.relationship("Team", backref="points_entry")

import itertools
import random
from flask import flash

def generate_fixtures(tournament):
    teams = Team.query.filter_by(tournament_id=tournament.id).all()

    if len(teams) < 2:
        flash("Not enough teams to generate fixtures!", "error")
        return None

    fixtures = []
    match_id = 1
    rounds = 1 if tournament.tournament_type == "Round Robin" else 2
    team_count = len(teams)

    # Generate balanced match schedule using round-robin algorithm
    schedule = []
    for _ in range(rounds):
        team_list = teams[:]  # Copy the team list
        if team_count % 2 == 1:
            team_list.append(None)  # Add a dummy team if odd number of teams
        num_rounds = len(team_list) - 1

        for r in range(num_rounds):
            match_round = []
            for i in range(len(team_list) // 2):
                team1, team2 = team_list[i], team_list[-(i + 1)]
                if team1 and team2:
                    match_round.append((team1.id, team2.id))  # Store match pairs
            schedule.append(match_round)
            # Rotate teams to balance the fixture
            team_list.insert(1, team_list.pop())
    i=1
    # Convert schedule into fixture list
    for match_round in schedule:
        for team1, team2 in match_round:
            fixtures.append({"label": str(i), "team1": team1, "team2": team2})
            match_id += 1
            i+=1

    return fixtures

def generate_playoff_fixtures(tournament, total_group_matches):
    """Generates playoff fixtures after all group matches are completed."""

    # **1️⃣ Count Total Matches Played in Tournament**
    total_matches_played = db.session.query(func.count(Fixture.id)).filter(
        Fixture.tournament_id == tournament.id
    ).scalar()

    # **2️⃣ Check If Playoff Matches Already Exist**
    if total_matches_played > total_group_matches:
        return None  # Playoff fixtures already exist, no need to generate again

    # **3️⃣ Check if All Group Matches Are Completed**
    completed_matches = db.session.query(func.count(Result.id)).join(Fixture).filter(
        Fixture.tournament_id == tournament.id
    ).scalar()

    if completed_matches < total_group_matches:
        return None  # Wait until all group matches are completed

    # **4️⃣ Find Last Match ID to Assign New Match IDs**
    last_match = db.session.query(Fixture.id).filter(
        Fixture.tournament_id == tournament.id
    ).order_by(Fixture.id.desc()).first()

    last_match_id = last_match.id if last_match else 0  # Default to 0 if no matches exist

    # **5️⃣ Fetch Teams Sorted by Points**
    teams = db.session.query(Team).join(PointsTable).filter(
        PointsTable.tournament_id == tournament.id
    ).order_by(
        PointsTable.points.desc(),
        (PointsTable.goals_scored - PointsTable.goals_conceded).desc(),
        PointsTable.wins.desc()
    ).all()

    team_count = len(teams)
    playoff_fixtures = []
    match_id = last_match_id + 1  # Start new playoff match IDs

    # **6️⃣ Generate Playoff Matches Based on Number of Teams**
    if team_count == 3:
        playoff_fixtures.append({"label": "Final", "team1": teams[0].id, "team2": teams[1].id})

    elif team_count in [4, 5]:
        semi_final = {"label": "Semi Final", "team1": teams[1].id, "team2": teams[2].id}
        playoff_fixtures.append(semi_final)
        match_id += 1
        final_match = {"label": "Final", "team1": teams[0].id, "team2": "Winner of Semi"}
        playoff_fixtures.append(final_match)

    elif team_count >= 6:
        semi1 = {"label": "Semi Final1", "team1": teams[0].id, "team2": teams[3].id}
        playoff_fixtures.append(semi1)
        match_id += 1
        semi2 = {"label": "Semi Final2", "team1": teams[1].id, "team2": teams[2].id}
        playoff_fixtures.append(semi2)
        match_id += 1
        final_match = {"label": "Final", "team1": "Winner of Semi 1", "team2": "Winner of Semi 2"}
        playoff_fixtures.append(final_match)
    return playoff_fixtures




def initialize_points_table(tournament_id):
    teams = Team.query.filter_by(tournament_id=tournament_id).all()
    new_entries = []

    for team in teams:
        if not PointsTable.query.filter_by(team_id=team.id, tournament_id=tournament_id).first():
            new_entries.append(PointsTable(
                tournament_id=tournament_id,
                team_id=team.id,
                wins=0,
                losses=0,
                draws=0,
                points=0,
                goals_scored=0,
                goals_conceded=0
            ))

    if new_entries:
        db.session.bulk_save_objects(new_entries)  # Efficient bulk insert
        db.session.commit()

import re

def natural_sort_key(label):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', label)]

def get_points_table(tournament_id):
    teams = PointsTable.query.filter_by(tournament_id=tournament_id).all()
    tournament=Tournament.query.get_or_404(tournament_id)

    # Compute Goal Difference (GD)
    for team in teams:
        team.goal_difference = team.goals_scored - team.goals_conceded

    # Sort Teams: Higher Points → Higher GD → Higher Goals Scored
    sorted_teams = sorted(teams, key=lambda x: (x.points, x.goal_difference, x.goals_scored), reverse=True)

    # Check if all group matches are completed
    teams_count = len(teams)
    if tournament.tournament_type == "Round Robin":
        total_group_matches = (teams_count * (teams_count - 1)) // 2
    elif tournament.tournament_type == "Double Round Robin":
        total_group_matches = (teams_count * (teams_count - 1))
    completed_matches = db.session.query(func.count(Result.id)).join(Fixture).filter(
        Fixture.tournament_id == tournament_id
    ).scalar()

    # Determine number of qualifying teams
    if teams_count == 3:
        qualifying_teams = 2
    elif 4 <= teams_count <= 5:
        qualifying_teams = 3
    else:
        qualifying_teams = 4 
    qualified_teams = set()
    if completed_matches >= total_group_matches:
        qualified_teams = {sorted_teams[i].team_id for i in range(qualifying_teams)}

    return sorted_teams, qualified_teams


from functools import wraps
from flask import session, redirect, url_for, flash

def role_required(roles):
    def wrapper(view_func):
        @wraps(view_func)
        def decorated_view(*args, **kwargs):
            if session.get("role") not in roles:
                return redirect(url_for("index"))
            return view_func(*args, **kwargs)
        return decorated_view
    return wrapper

# Login Route
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        user = User.query.filter_by(username=username).first()
        if user and role == "guest":
            # Guest login: No password, assign role
            session["user"] = username
            session["user_id"] = user.id
            session["role"] = "guest"
            return redirect(url_for("index"))

        # Regular login
        
        if user and password == user.password_hash:
            session["user"] = username
            session["user_id"] = user.id
            session["role"] = "admin"  # Or user.role if you store it in DB
            return redirect(url_for("index"))

        flash("Invalid credentials. Try again.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


# Signup Route
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("User already exists. Try a different username.", "warning")
            return redirect(url_for("signup"))

        #hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=password)
        db.session.add(new_user)
        db.session.commit()

        session["user"] = username  # Auto-login after signup
        session["user_id"] = new_user.id
        session["role"] = 'admin'
        return redirect(url_for("index"))

    return render_template("signup.html")

@app.route('/index')
def index():
    if "user" not in session:
        return redirect(url_for("login"))  # Redirect to login if not logged in

    user_id = session["user_id"]
    tournaments = Tournament.query.filter_by(user_id=user_id).all()
    
    return render_template('index.html', tournaments=tournaments)

@app.route("/logout")
def logout():
    """Logout user and clear session."""
    session.pop("user", None)
    session.pop("user_id", None)
    return redirect(url_for("login"))

@app.route('/add_tournament', methods=['GET', 'POST'])
@role_required(['admin'])
def add_tournament():
    """Allow logged-in users to add a tournament linked to their account."""
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == 'POST':
        name = request.form['name']
        tournament_type = request.form['tournament_type']
        num_teams = request.form['num_teams']
        user_id = session["user_id"]  # Associate tournament with logged-in user

        new_tournament = Tournament(name=name, tournament_type=tournament_type, num_teams=num_teams, user_id=user_id)
        db.session.add(new_tournament)
        db.session.commit()

        return redirect(url_for('index'))
    
    return render_template('add_tournament.html')


@app.route('/tournament/<int:tournament_id>')
def team_details(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    teams = Team.query.filter_by(tournament_id=tournament_id).all()
    if not teams:
        return redirect(url_for('add_teams', tournament_id=tournament_id))
    return render_template('team_details.html', tournament=tournament, teams=teams)

@app.route('/tournament/<int:tournament_id>/teams', methods=['GET', 'POST'])
@role_required(['admin'])
def add_teams(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if request.method == 'POST':
        team_names = [request.form[f'team{i}'] for i in range(1, tournament.num_teams + 1)]
        
        for name in team_names:
            new_team = Team(name=name, tournament_id=tournament_id)
            db.session.add(new_team)
        
        db.session.commit()

        # Initialize points table for this tournament
        initialize_points_table(tournament_id)
        return redirect(url_for('team_details', tournament_id=tournament_id))

    return render_template('add_teams.html', tournament=tournament)

from flask import request, jsonify

@app.route('/edit_team/<int:team_id>', methods=['POST'])
@role_required(['admin'])
def edit_team(team_id):
    team = Team.query.get_or_404(team_id)
    data = request.get_json()
    team.name = data['name']
    db.session.commit()
    return jsonify({"message": "Team name updated successfully"})



import time

@app.route('/get_fixtures/<int:tournament_id>', methods=['GET'])
def get_fixtures(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    teams_count = Team.query.filter_by(tournament_id=tournament.id).count()

    if tournament.tournament_type == "Round Robin":
        total_group_matches = (teams_count * (teams_count - 1)) // 2
    elif tournament.tournament_type == "Double Round Robin":
        total_group_matches = teams_count * (teams_count - 1)
    else:
        total_group_matches = 0  

    completed_matches = db.session.query(func.count(Result.id)).join(Fixture).filter(
        Fixture.tournament_id == tournament_id
    ).scalar()

    if completed_matches == total_group_matches:
        total_tournament_fixtures = db.session.query(func.count(Fixture.id)).filter(
            Fixture.tournament_id == tournament.id
        ).scalar()

        if total_tournament_fixtures == total_group_matches:
            playoff_fixtures = generate_playoff_fixtures(tournament, total_group_matches)

            for fixture in playoff_fixtures:
                new_fixture = Fixture(
                    tournament_id=tournament.id,
                    team1_id=fixture["team1"] if isinstance(fixture["team1"], int) else None,
                    team2_id=fixture["team2"] if isinstance(fixture["team2"], int) else None,
                    label=fixture['label']
                )
                db.session.add(new_fixture)

            db.session.commit()
            time.sleep(1)  

    fixtures = Fixture.query.filter_by(tournament_id=tournament_id).order_by(Fixture.id).all()

    
    if not fixtures:
        generated_fixtures = generate_fixtures(tournament)
        if generated_fixtures:
            new_fixtures = [
                Fixture(
                    tournament_id=tournament.id,
                    team1_id=fixture["team1"],
                    team2_id=fixture["team2"],
                    label=fixture['label']
                )
                for fixture in generated_fixtures
            ]
            db.session.bulk_save_objects(new_fixtures)
            db.session.commit()
            time.sleep(1)  
            fixtures = Fixture.query.filter_by(tournament_id=tournament_id).order_by(Fixture.id).all()


    fixture_list = []
    semifinal_winners = []
    for index, fixture in enumerate(fixtures):
        team1 = Team.query.get(fixture.team1_id) if fixture.team1_id else None
        team2 = Team.query.get(fixture.team2_id) if fixture.team2_id else None
        label = fixture.label

        if "Semi Final" in label and fixture.winner:
            winner=fixture.winner
            if 'Penal' in fixture.winner:
                winner=winner.split()[0]
            winner_team = Team.query.filter_by(name=winner).first()
            if winner_team:
                semifinal_winners.append([winner_team.id,winner_team])
        elif label=="Final" and (team1 is None or team2 is None):
            if len(semifinal_winners) == 2:
                if fixture.team1_id is None:
                    fixture.team1_id = semifinal_winners[1][0]
                    team1=semifinal_winners[1][1]
                if fixture.team2_id is None:
                    fixture.team2_id = semifinal_winners[0][0]
                    team1=semifinal_winners[0][1]
            elif len(semifinal_winners) == 1:
                if fixture.team2_id is None:
                    fixture.team2_id = semifinal_winners[0][0]
                    team1=semifinal_winners[0][1]
            db.session.commit()
            time.sleep(1)
        
        fixture_list.append({
            "id": fixture.id,
            "match_number": index + 1,
            "label": label,
            "team1": team1.name if team1 else "TBD",
            "team2": team2.name if team2 else "TBD",
            "winner": (fixture.winner).split()[0] if fixture.winner else None
        })
    fixture_list.sort(key=lambda x: x["id"])
    return render_template('fixtures_details.html', tournament=tournament, fixture_list=fixture_list)


@app.route('/team/<int:team_id>/players', methods=['GET', 'POST'])
@role_required(['admin'])
def register_players(team_id):
    team = Team.query.get_or_404(team_id)
    tournament = Tournament.query.get_or_404(team.tournament_id)
    players = Player.query.filter_by(team_id=team.id).all()

    if request.method == 'POST':
        # Only allow registration if players do not already exist.
        num_players = int(request.form.get('num_players', 0))
        for i in range(1, num_players + 1):
            name = request.form.get(f'playerName_{i}')
            position = request.form.get(f'position_{i}')
            if name and position:
                new_player = Player(name=name, position=position, team_id=team.id)
                db.session.add(new_player)
        db.session.commit()
        return redirect(url_for('register_players', team_id=team.id))
    return render_template('players_registration.html',tournament=tournament, team=team, players=players)


@app.route('/edit_player/<int:player_id>', methods=['POST'])
@role_required(['admin'])
def edit_player(player_id):
    player = Player.query.get_or_404(player_id)
    data = request.get_json()
    if 'name' in data and 'position' in data:
        player.name = data['name'].strip()
        player.position = data['position'].strip()
        db.session.commit()
        return jsonify({"message": "Player updated successfully"}), 200
    return jsonify({"message": "Invalid data"}), 400

@app.route('/match/<int:fixture_id>', methods=['GET', 'POST'])
def conduct_match(fixture_id):
    fixture = Fixture.query.get_or_404(fixture_id)
    team1 = Team.query.get_or_404(fixture.team1_id)
    team2 = Team.query.get_or_404(fixture.team2_id)

    # Fetch or create result entry
    result = Result.query.filter_by(fixture_id=fixture.id).first()
    if not result:
        result = Result(fixture_id=fixture.id)
        db.session.add(result)
        db.session.commit()

    players_team1 = Player.query.filter_by(team_id=team1.id).all()
    players_team2 = Player.query.filter_by(team_id=team2.id).all()

    if request.method == 'POST':
        scoring_team = request.form.get('scoring_team')
        scoring_player_id = request.form.get('scoring_player')

        # Update score in the results table
        if scoring_team == 'team1':
            result.team1_score += 1
        elif scoring_team == 'team2':
            result.team2_score += 1

        # Save goal scorer
        goal_scorer = Player.query.get(scoring_player_id)
        if goal_scorer:
            goal_scorer.goals += 1  # Assuming 'goals' field exists in Player model

        db.session.commit()
        return redirect(url_for('conduct_match', fixture_id=fixture_id))

    return render_template('match.html', fixture=fixture, team1=team1, team2=team2, 
                           result=result, players_team1=players_team1, players_team2=players_team2)

@app.route('/update_score/<int:fixture_id>', methods=['POST'])
def update_score(fixture_id):
    fixture = Fixture.query.get_or_404(fixture_id)
    result = Result.query.filter_by(fixture_id=fixture.id).first()

    data = request.get_json()
    scoring_team = data.get("scoring_team")
    player_id = data.get("player_id")

    if scoring_team == "team1":
        result.team1_score += 1
    elif scoring_team == "team2":
        result.team2_score += 1

    # Update Player's Goal Count
    player = Player.query.get(player_id)
    if player:
        player.goals += 1  # Assuming goals column exists in Player model

    db.session.commit()

    return jsonify({"team1_score": result.team1_score, "team2_score": result.team2_score})

@app.route('/end_match/<int:fixture_id>', methods=['POST'])
def end_match(fixture_id):
    fixture = Fixture.query.get_or_404(fixture_id)
    
    # Extract goals from JSON request
    data = request.get_json()
    team1_goals = data.get("team1_goals", [])  # List of player IDs for Team 1
    team2_goals = data.get("team2_goals", [])  # List of player IDs for Team 2

    # Store goal details in fixture
    fixture.goals = json.dumps({
        "team1": team1_goals,
        "team2": team2_goals
    })

    # Calculate scores
    team1_score = len(team1_goals)
    team2_score = len(team2_goals)

    fixture.team1_score = team1_score
    fixture.team2_score = team2_score

    tournament = Tournament.query.get_or_404(fixture.tournament_id)
    total_teams = tournament.num_teams  # Total number of teams

    # Determine total group matches based on tournament type
    if tournament.tournament_type == "Round Robin":
        total_group_matches = (total_teams * (total_teams - 1)) // 2
    elif tournament.tournament_type == "Double Round Robin":
        total_group_matches = (total_teams * (total_teams - 1))
    else:
        total_group_matches = 0

    # Count total completed matches so far
    completed_matches = Fixture.query.filter(
        Fixture.tournament_id == fixture.tournament_id,
        Fixture.winner.isnot(None)
    ).count()

    is_playoff = completed_matches >= total_group_matches  # True if match is playoff

    # Determine match result
    if team1_score > team2_score:
        fixture.winner = fixture.team1.name
    elif team2_score > team1_score:
        fixture.winner = fixture.team2.name
    else:
        fixture.winner = "Draw"
    db.session.commit()
    # **Only update points table if it's a group stage match**
    if not is_playoff:
        team1_entry = PointsTable.query.filter_by(tournament_id=fixture.tournament_id,team_id=fixture.team1_id).first()
        team2_entry = PointsTable.query.filter_by(tournament_id=fixture.tournament_id,team_id=fixture.team2_id).first()

        # Update goals scored & conceded
        team1_entry.goals_scored += team1_score
        team1_entry.goals_conceded += team2_score
        team2_entry.goals_scored += team2_score
        team2_entry.goals_conceded += team1_score

        # Update wins, losses, draws, and points only for group stage
        if team1_score > team2_score:
            team1_entry.wins += 1
            team1_entry.points += 3
            team2_entry.losses += 1
        elif team2_score > team1_score:
            team2_entry.wins += 1
            team2_entry.points += 3
            team1_entry.losses += 1
        elif team1_score == team2_score:
            team1_entry.draws += 1
            team2_entry.draws += 1
            team1_entry.points += 1
            team2_entry.points += 1

        db.session.commit()
    return jsonify({
        "success": True,
        "winner": fixture.winner,
        "team1_score": team1_score,
        "team2_score": team2_score,
        "is_playoff": is_playoff,
        "go_to_penalty": is_playoff and team1_score == team2_score
    })



@app.route('/results/<int:tournament_id>', methods=['GET'])
def match_results(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    # Get all completed fixtures (matches with a winner)


    fixtures = Fixture.query.filter(
        Fixture.tournament_id == tournament_id,
        Fixture.winner.isnot(None)
    ).order_by(desc(Fixture.id)).limit(6).all()


    results = []
    
    for index, fixture in enumerate(fixtures):
        team1 = Team.query.get(fixture.team1_id)
        team2 = Team.query.get(fixture.team2_id)
        goal_data = fixture.get_goals()

        team1_scorers = [Player.query.get(player_id).name for player_id in goal_data.get("team1", [])]
        team2_scorers = [Player.query.get(player_id).name for player_id in goal_data.get("team2", [])]

        # Assign labels only to playoff matches
        label = fixture.label
        winner=fixture.winner
        penal=''
        if 'Penal' in winner:
            w=winner.split()
            winner=w[0]
            penal=w[1]
        results.append({
            "team1": team1.name if team1 else "TBD",
            "team2": team2.name if team2 else "TBD",
            "team1_score": len(team1_scorers),
            "team2_score": len(team2_scorers),
            "team1_scorers": team1_scorers,
            "team2_scorers": team2_scorers,
            "winner": winner,  
            "penal": penal,
            "label": label  
        })

    return render_template('results.html', tournament=tournament, results=results)



@app.route('/points_table/<int:tournament_id>')
def points_table(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Get sorted teams & qualified teams separately
    points_table, qualified_teams = get_points_table(tournament_id)
    
    return render_template("pointstable.html", tournament=tournament, points_table=points_table, qualified_teams=qualified_teams)


@app.route('/top_scorers/<int:tournament_id>')
def top_scorers(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)

    # Fetch top 10 players with highest goals from the tournament
    top_scorers = Player.query.join(Team, Player.team_id == Team.id) \
                          .filter(Team.tournament_id == tournament_id) \
                          .order_by(Player.goals.desc()) \
                          .limit(10).all()

    return render_template("player_stats.html", tournament=tournament, top_scorers=top_scorers)

@app.route('/conduct-penalty/<int:fixture_id>')
def conduct_penalty(fixture_id):
    fixture = Fixture.query.get_or_404(fixture_id)
    
    team1 = Team.query.get_or_404(fixture.team1_id)
    team2 = Team.query.get_or_404(fixture.team2_id)

    return render_template('penalty.html', fixture=fixture, team1=team1, team2=team2)


@app.route("/end_penalty/<int:fixture_id>", methods=["POST"])
def end_penalty(fixture_id):
    # Get data from the frontend
    data = request.get_json()
    team1_goals = data['team1_goals']
    team2_goals = data['team2_goals']
    
    # Fetch the fixture from the database
    fixture = Fixture.query.get(fixture_id)
    
    # Determine the winner
    if team1_goals > team2_goals:
        winner = fixture.team1.name
    elif team2_goals > team1_goals:
        winner = fixture.team2.name
    else:
        winner = "Draw"
    fixture.winner=winner+f' Penalties:({team1_goals}-{team2_goals})'
    db.session.commit()
    time.sleep(1)
    # Return the updated scores and winner
    return jsonify({
        "team1_score": team1_goals,
        "team2_score": team2_goals,
        "winner": winner
    })



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
