from flask import Blueprint
from flask import Flask, render_template, url_for, request, redirect, send_file, jsonify, abort
from db import db
from db_serve import Serve, ServeAnalysis, ServeStatus
from db_tennis import Tennis, TennisAnalysis, TennisStatus
from db_match import Match
from db_player import Player
from datetime import datetime, timedelta
from sqlalchemy import func, extract
from sqlalchemy import cast, String, desc
from utils import test_connection, user_dict, get_week_range, get_client_time, get_match_round_abbreviation, generate_title, extract_number_from_string
from flask_login import login_required
import math
from sqlalchemy.orm import aliased
import re
import os
from azure.storage.fileshare import ShareFileClient, ShareServiceClient
from azure.core.exceptions import ResourceNotFoundError
from io import BytesIO

match_bp = Blueprint('match', __name__)

@match_bp.route('/match')
@login_required
def match_index():
    player_id = request.args.get('u')
    player1 = aliased(Player)
    player2 = aliased(Player)
    player3 = aliased(Player)
    player4 = aliased(Player)

    match_query = db.session.query(
        Match,
        player1.first_name.label('player1_first_name'), player1.last_name.label('player1_last_name'),
        player2.first_name.label('player2_first_name'), player2.last_name.label('player2_last_name'),
        player3.first_name.label('player3_first_name'), player3.last_name.label('player3_last_name'),
        player4.first_name.label('player4_first_name'), player4.last_name.label('player4_last_name')
    ).join(player1, Match.player1 == player1.id, isouter=True) \
    .join(player2, Match.player2 == player2.id, isouter=True) \
    .join(player3, Match.player3 == player3.id, isouter=True) \
    .join(player4, Match.player4 == player4.id, isouter=True) \
    .filter(Match.player1 == player_id) \
    .order_by(desc(Match.date), desc(Match.id)) \
    .all()

    results = []
    last_match_name = None
    for match in match_query:
        if match.Match.type == 'S':
            team1_name = f"{match.player1_first_name} {match.player1_last_name}"
            team2_name = f"{match.player2_first_name} {match.player2_last_name}"
        else:  # Assuming 'Doubles'
            team1_name = get_name_short(match.player1_first_name, match.player1_last_name) + " / " + get_name_short(match.player3_first_name, match.player3_last_name)
            team2_name = get_name_short(match.player2_first_name, match.player2_last_name) + " / " + get_name_short(match.player4_first_name, match.player4_last_name)
            
        if match.Match.player1_seed:
                team1_name += f" [{match.Match.player1_seed}]"
        if match.Match.player2_seed:
                team2_name += f" [{match.Match.player2_seed}]"

        round_name = get_match_round_abbreviation(match.Match)

        tournament_logo = generate_title(match.Match.match_name)

        event_name = extract_number_from_string(match.Match.match_event)

        match_data = {
            'match': match.Match,
            'player1_first_name': match.player1_first_name,
            'player1_last_name': match.player1_last_name,
            'player2_first_name': match.player2_first_name,
            'player2_last_name': match.player2_last_name,
            'player3_first_name': match.player3_first_name,
            'player3_last_name': match.player3_last_name,
            'player4_first_name': match.player4_first_name,
            'player4_last_name': match.player4_last_name,
            'team1_name': team1_name,
            'team2_name': team2_name,
            'round_name': round_name,
            'tournament_logo': tournament_logo,
            'event_name': event_name,
            'show_match_name': match.Match.match_name != last_match_name
        }
        results.append(match_data)
        last_match_name = match.Match.match_name

    return render_template('match.html', results=results)

def get_name_short(first_name, last_name):
    name = f"{first_name} {last_name[0]}" if last_name else first_name
    return name if name else ''

@match_bp.route('/match/logo/<string:image_id>')
def get_logo(image_id):
    file_share_name = "bhmfiles"
    folder_name = "tennis/logo"
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    try:
        
        service_client = ShareServiceClient.from_connection_string(connection_string)
        directory_client = service_client.get_share_client(file_share_name).get_directory_client(folder_name)
        file_client = directory_client.get_file_client(f"{image_id}.png")
        stream = file_client.download_file()
        # Create a BytesIO object to store the downloaded content
        content = BytesIO()
        content.write(stream.readall())

        # Seek back to the beginning of the BytesIO object
        content.seek(0)

        # Return the image file
        return send_file(content, mimetype='image/png')

    except ResourceNotFoundError:
        # If image_id.png is not found, return usta.png
        try:
            directory_client = service_client.get_share_client(file_share_name).get_directory_client(folder_name)
            file_client = directory_client.get_file_client("usta.png")
            stream = file_client.download_file()
            # Create a BytesIO object to store the downloaded content
            content = BytesIO()
            content.write(stream.readall())

            # Seek back to the beginning of the BytesIO object
            content.seek(0)

            # Return the image file
            return send_file(content, mimetype='image/png')
        except ResourceNotFoundError:
            # If usta.png is also not found, return a generic 404 image or handle as needed
            abort(404)