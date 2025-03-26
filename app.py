from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tournament.db'
db = SQLAlchemy(app)

class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tournament_type = db.Column(db.String(50), nullable=False)
    num_teams = db.Column(db.Integer, nullable=False)

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
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
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

    # Convert schedule into fixture list
    for match_round in schedule:
        for team1, team2 in match_round:
            fixtures.append({"match_id": match_id, "team1": team1, "team2": team2})
            match_id += 1

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
        playoff_fixtures.append({"match_id": match_id, "team1": teams[0].id, "team2": teams[1].id})

    elif team_count in [4, 5]:
        semi_final = {"match_id": match_id, "team1": teams[1].id, "team2": teams[2].id}
        playoff_fixtures.append(semi_final)
        match_id += 1
        final_match = {"match_id": match_id, "team1": teams[0].id, "team2": "Winner of Semi"}
        playoff_fixtures.append(final_match)

    elif team_count >= 6:
        semi1 = {"match_id": match_id, "team1": teams[0].id, "team2": teams[3].id}
        playoff_fixtures.append(semi1)
        match_id += 1
        semi2 = {"match_id": match_id, "team1": teams[1].id, "team2": teams[2].id}
        playoff_fixtures.append(semi2)
        match_id += 1
        final_match = {"match_id": match_id, "team1": "Winner of Semi 1", "team2": "Winner of Semi 2"}
        playoff_fixtures.append(final_match)

    # **7️⃣ Save Playoff Fixtures to Database**
    for fixture in playoff_fixtures:
        new_fixture = Fixture(
            tournament_id=tournament.id,
            team1_id=fixture["team1"] if isinstance(fixture["team1"], int) else None,
            team2_id=fixture["team2"] if isinstance(fixture["team2"], int) else None
        )
        db.session.add(new_fixture)

    db.session.commit()
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



def get_points_table(tournament_id):
    teams = PointsTable.query.filter_by(tournament_id=tournament_id).all()

    # Compute Goal Difference (GD)
    for team in teams:
        team.goal_difference = team.goals_scored - team.goals_conceded

    # Sort Teams: Higher Points → Higher GD → Higher Goals Scored
    sorted_teams = sorted(teams, key=lambda x: (x.points, x.goal_difference, x.goals_scored), reverse=True)

    return sorted_teams



# Hardcoded credentials
USERNAME = "umeshkhanal"
PASSWORD = "umeshkhanal912"

@app.route("/", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("index"))  # Redirect if already logged in

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == USERNAME and password == PASSWORD:
            session["user"] = username
            return redirect(url_for("index"))

        return "Invalid credentials. Try again."

    return render_template("login.html")

@app.route('/index')
def index():
    if "user" not in session:
        return redirect(url_for("login"))  # Redirect to login if not logged in

    tournaments = Tournament.query.all()
    return render_template('index.html', tournaments=tournaments)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


@app.route('/add_tournament', methods=['GET', 'POST'])
def add_tournament():
    if request.method == 'POST':
        name = request.form['name']
        tournament_type = request.form['tournament_type']
        num_teams = request.form['num_teams']
        new_tournament = Tournament(name=name, tournament_type=tournament_type, num_teams=num_teams)
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

    # Fetch all fixtures
    fixtures = Fixture.query.filter_by(tournament_id=tournament_id).all()
    
    teams_count = Team.query.filter_by(tournament_id=tournament.id).count()

    if tournament.tournament_type == "Round Robin":
        total_group_matches = (teams_count * (teams_count - 1)) // 2  # Single round
    elif tournament.tournament_type == "Double Round Robin":
        total_group_matches = teams_count * (teams_count - 1)  # Double round
    else:
        total_group_matches = 0  # Other formats (like Knockout) are not considered here
    
    completed_matches = db.session.query(func.count(Result.id)).join(Fixture).filter(
        Fixture.tournament_id == tournament_id
    ).scalar()

    if completed_matches == total_group_matches:
        # **1️⃣ Count total fixtures for this tournament**
        total_tournament_fixtures = db.session.query(func.count(Fixture.id)).filter(
            Fixture.tournament_id == tournament.id
        ).scalar()

        # **2️⃣ Check if playoffs already exist**
        if total_tournament_fixtures > total_group_matches:
            # Fetch only **playoff fixtures** (matches beyond group stage)
            playoff_fixtures = db.session.query(Fixture).filter(
                Fixture.tournament_id == tournament.id
            ).order_by(Fixture.id.asc()).offset(total_group_matches).all()
        else:
            # Generate new playoffs if they don’t exist
            playoff_fixtures = generate_playoff_fixtures(tournament, total_group_matches)
        
        time.sleep(1)  # Ensure DB commit completes
        fixture_list = []
        num_fixtures = len(playoff_fixtures)

        # **3️⃣ Process fixtures & assign labels**
        for index, fixture in enumerate(playoff_fixtures):
            team1 = Team.query.get(fixture.team1_id) if fixture.team1_id else None
            team2 = Team.query.get(fixture.team2_id) if fixture.team2_id else None

            # **Assign match labels based on the number of playoff matches**
            label = None
            if num_fixtures == 1:
                label = "Final"
            elif num_fixtures == 2:
                label = "Semifinal"
            elif num_fixtures == 3:
                if index == 0:
                    label = "Semifinal 1"
                elif index == 1:
                    label = "Semifinal 2"
                else:
                    label = "Final"

            fixture_list.append({
                "id": fixture.id,
                "match_number": fixture.id,  # Match ID from database
                "team1": team1.name if team1 else "TBD",
                "team2": team2.name if team2 else "TBD",
                "winner": fixture.winner if fixture.winner else None,
                "label": label
            })

        return render_template('fixtures_details.html', tournament=tournament, fixture_list=fixture_list)



    # If group stage isn't completed, show normal fixtures
    if not fixtures:
        generated_fixtures = generate_fixtures(tournament)
        if generated_fixtures:
            new_fixtures = [
                Fixture(
                    tournament_id=tournament.id,
                    team1_id=fixture["team1"],
                    team2_id=fixture["team2"]
                )
                for fixture in generated_fixtures
            ]
            db.session.bulk_save_objects(new_fixtures)
            db.session.commit()
            time.sleep(1)  # Ensure DB commit completes
            
            fixtures = Fixture.query.filter_by(tournament_id=tournament_id).all()  # Reload data

    fixture_list = []
    for index, fixture in enumerate(fixtures):
        team1 = Team.query.get(fixture.team1_id) if fixture.team1_id else None
        team2 = Team.query.get(fixture.team2_id) if fixture.team2_id else None
        label = None

        # Check if it's beyond group stage
        if index >= total_group_matches:
            knockout_index = index - total_group_matches
            num_fixtures = len(fixtures) - total_group_matches

            if num_fixtures == 1:
                label = "Final"
            elif num_fixtures == 2:
                label = "Semifinal"
            elif num_fixtures == 3:
                if knockout_index == 0:
                    label = "Semifinal 1"
                elif knockout_index == 1:
                    label = "Semifinal 2"
                else:
                    label = "Final"
            else:
                label = f"Knockout Match {knockout_index + 1}"

        fixture_list.append({
            "id": fixture.id,
            "match_number": index + 1,
            "label": label if label else "Group Stage",
            "team1": team1.name if team1 else "TBD",
            "team2": team2.name if team2 else "TBD",
            "winner": fixture.winner if fixture.winner else None
        })

    return render_template('fixtures_details.html', tournament=tournament, fixture_list=fixture_list)




@app.route('/team/<int:team_id>/players', methods=['GET', 'POST'])
def register_players(team_id):
    team = Team.query.get_or_404(team_id)
    tournament = Tournament.query.get_or_404(team.tournament_id)
    players = Player.query.filter_by(team_id=team.id).all()

    if request.method == 'POST' and not players:
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

    # Get PointsTable entries
    team1_entry = PointsTable.query.filter_by(team_id=fixture.team1_id, tournament_id=fixture.tournament_id).first()
    team2_entry = PointsTable.query.filter_by(team_id=fixture.team2_id, tournament_id=fixture.tournament_id).first()

    # Update goals scored & conceded
    team1_entry.goals_scored += team1_score
    team1_entry.goals_conceded += team2_score
    team2_entry.goals_scored += team2_score
    team2_entry.goals_conceded += team1_score

    # Determine match result and update points
    if team1_score > team2_score:
        fixture.winner = fixture.team1.name
        team1_entry.wins += 1
        team1_entry.points += 3
        team2_entry.losses += 1
    elif team2_score > team1_score:
        fixture.winner = fixture.team2.name
        team2_entry.wins += 1
        team2_entry.points += 3
        team1_entry.losses += 1
    else:
        fixture.winner = "Draw"
        team1_entry.draws += 1
        team2_entry.draws += 1
        team1_entry.points += 1
        team2_entry.points += 1

    db.session.commit()
    return jsonify({
        "success": True,
        "winner": fixture.winner,
        "team1_score": team1_score,
        "team2_score": team2_score
    })


@app.route('/results/<int:tournament_id>', methods=['GET'])
def match_results(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    fixtures = Fixture.query.filter(Fixture.tournament_id == tournament_id, Fixture.winner.isnot(None)).all()

    results = []
    match_no=1
    for fixture in fixtures:
        team1 = Team.query.get(fixture.team1_id)
        team2 = Team.query.get(fixture.team2_id)
        goal_data = fixture.get_goals()

        team1_scorers = [Player.query.get(player_id).name for player_id in goal_data.get("team1", [])]
        team2_scorers = [Player.query.get(player_id).name for player_id in goal_data.get("team2", [])]

        results.append({
            "match_id": match_no,
            "team1": team1.name,
            "team2": team2.name,
            "team1_score": len(team1_scorers),
            "team2_score": len(team2_scorers),
            "team1_scorers": team1_scorers,
            "team2_scorers": team2_scorers,
            "winner": fixture.winner  # Winner is now stored as team name
        })
        match_no+=1

    return render_template('results.html', tournament=tournament, results=results)

@app.route('/points_table/<int:tournament_id>')
def points_table(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    points_table = get_points_table(tournament_id)
    return render_template("pointstable.html", tournament=tournament, points_table=points_table)

@app.route('/top_scorers/<int:tournament_id>')
def top_scorers(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)

    # Fetch top 10 players with highest goals from the tournament
    top_scorers = Player.query.join(Team, Player.team_id == Team.id) \
                          .filter(Team.tournament_id == tournament_id) \
                          .order_by(Player.goals.desc()) \
                          .limit(5).all()

    return render_template("player_stats.html", tournament=tournament, top_scorers=top_scorers)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
