from flask import Flask, request, make_response, jsonify
import os
import json
import requests
from slackclient import SlackClient
from pytz import timezone

# set your local timezone if the server is running on cloud
tz = timezone('US/Eastern')


# Your app's Slack bot user token
SLACK_BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']
slack_client = SlackClient(SLACK_BOT_TOKEN)
port = os.getenv("PORT") or 5000

# Flask webserver for incoming traffic from Slack
app = Flask(__name__)
header = {"Content-Type": "application/json"}
circleci_token = os.environ['CIRCLECI_TOKEN']
url_tree = "https://circleci.com/api/v1.1/project/github/:username/:project/tree/"
info = {"message_ts": ""}

trigger_info = [
    "build_trigger"
]


# send button for user to open dialog menu
# you can add more different dialog menus and slack commands here
def send_dialog_button(data):
    channel_id = data['channel_id']
    command = data.get('text')
    # you can configure your slack commands, here we set `/test build` in command
    if 'build' in command:
        with open('slack_trigger_dialog.json', 'r') as file:
            slack_message = json.load(file)
        order_dm = slack_client.api_call(
          "chat.postMessage",
          as_user=True,
          channel=channel_id,
          text="Let\'s make a build for a test!",
          attachments=slack_message['attachments']
        )
        print(order_dm)
        return
    return jsonify({"text": "`invalid command` " + "please type: *build*"})


# open dialog menu, user can select different parameters from dropdown lists and input text field
def open_dialog_menu(dialog, message_action, github_url):
    response = requests.get("https://circleci.com/api/v1.1/projects?circle-token=" + circleci_token)
    results = json.loads(response.text)
    for project in results:
            if project['vcs_url'] == github_url:
                branches = project["branches"].keys()
    for branch in branches:
        if branch != "master":
            if message_action["actions"][0]["name"] in trigger_info:
                dialog['dialog']['elements'][3]['options'].append({"label": branch, "value": branch})
    open_dialog = slack_client.api_call(
        "dialog.open",
        trigger_id=message_action["trigger_id"],
        dialog=dialog['dialog']
    )
    print(open_dialog)


# collect custom info from selected options, trigger build via circleci api
def api_trigger_circlebuild(message_action):
    user = message_action['user']['name']
    channel_id = message_action['channel']['id']
    suite = message_action['submission']['suite_preferences']
    platform = message_action['submission']['platform_preferences']
    branch = message_action['submission']['branch_preferences']
    url = url_tree + branch + "?circle-token=" + circleci_token
    payload = {
        "build_parameters": {
            "suite": suite,
            "PLATFORM": platform,
            'USER': user
        }
    }
    if message_action['submission']['url'] is not None:
        payload["build_parameters"]["URL"] = message_action['submission']['url']
    result = requests.post(url, data=json.dumps(payload), headers=header)
    return result, user, suite, branch, channel_id


@app.route("/", methods=["POST"])
def message_actions():
    # Parse the request payload
    data = request.form

    # slack commands have not `payload` in data
    # init a slack dialog to custom build
    if 'payload' not in data:
        send_dialog_button(data)
        return make_response("", 200)

    message_action = json.loads(request.form["payload"])

    # receive post requests from slack button
    if message_action["type"] == "interactive_message":
        # open dialog menu, here you can expand more dialog for different tests
        if message_action["actions"][0]["name"] in trigger_info:
            info["message_ts"] = message_action["message_ts"]
            github_url = "https://github.com/:username/:Project"
            if message_action["actions"][0]["name"] == "build_trigger":
                with open('slack_dialog.json', 'r') as file:
                    dialog = json.load(file)
            open_dialog_menu(dialog, message_action, github_url)

    # receive post requests from slack dialog interactive message
    # trigger build via circleci api
    # sample dialog menu payload see slack_dialog.json
    elif message_action["type"] == "dialog_submission":
        result, user, suite, branch, channel_id = api_trigger_circlebuild(message_action)

        if result.status_code == 201:
            with open('slack_trigger_dialog.json', 'r') as file:
                new_message = json.load(file)
                new_message['attachments'][0]['fields'] = [{
                    'title': "@" + user + ' build test: ' + suite + 'at git branch ' + branch,
                    'short': False
                }]
            slack_client.api_call(
                "chat.update",
                channel=channel_id,
                ts=info["message_ts"],
                text="Customized tests built!",
                attachments=new_message['attachments']
            )
    return make_response("", 200)


@app.route('/errors', methods=['POST'])
def errors():
    print(json.loads(request.get_data()))
    return jsonify(status=200)


app.run(port=port, debug=True)
