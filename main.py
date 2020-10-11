from flask import Flask, render_template, redirect, request,session,make_response
import requests
import json
import datetime
import time
import os
import random
import sys
from google.cloud import storage


app = Flask(__name__)
app.secret_key = 'a slug eating lettuce is fast and bulbous'
client_id = "54603"
client_secret = "b07bec06258ecb8870ab9950af40b2a2066974fd"
# Assume running in gcloud
debug = False
try:
    gcstorage_client = storage.Client()
    gcbucket = gcstorage_client.bucket("straview.appspot.com")
except:
    print("\n CANNOT connect to gcloud")

port = 80
gcloud = True
#host = "straview.uk.to"
host = "straview.oa.r.appspot.com"

if (len(sys.argv) > 1 and sys.argv[1] == "prod"):
    host = "localhost"
    debug = False
    port = 80
    gcloud = False
elif (len(sys.argv) > 1 and sys.argv[1] == "dev"):
    host = "localhost"
    debug = True
    port = 8002
    gcloud = False

redirecturl = "https://www.strava.com/oauth/authorize?client_id=54603&redirect_uri=http://" + host + ":" + str(port) + "/login2&response_type=code&scope=read,activity:read_all&approval_prompt=auto&state=private"
print("Will use this to redirect:",redirecturl)
    



def putStringFile(s, file, public):
    if (gcloud):
        blob = gcbucket.blob(file)
        if (public):
            blob.upload_from_string(s,predefined_acl='publicRead')
        else:
            blob.upload_from_string(s)
    else:
        with open(file, 'w') as outfile:
            outfile.write(s)

def get_strava_tokens():
    stravaid = session['stravaid']
    file = 'data/strava_tokens_' + str(stravaid) + '.json'
    if (gcloud):
        blob = gcbucket.blob(file)
        strava_tokens = json.loads(blob.download_as_string(file))
    else:
        with open(file) as json_file:
            strava_tokens = json.load(json_file)
    return strava_tokens

@app.route('/')
def index():
    if 'firstname' in session:
        resp = make_response(render_template('index2.html', name = session['firstname']))
        return resp
    else:
        known = request.cookies.get('known')
        if (known and (known == '1')):
            # we know he has been authorised before so log him in
            return redirect(redirecturl, code=302)

    resp = make_response(render_template('index.html', url=redirecturl))
    resp.set_cookie('known', '0', expires=datetime.datetime.now() + datetime.timedelta(days=1000))
    return resp 

#https://www.strava.com/oauth/authorize?client_id=36&scope=read,read_all,profile:read_all,profile:write,activity:read,
#activity:read_all,activity:write&redirect_uri=https://veloviewer.com/&response_type=code&approval_prompt=auto&state=private


@app.route('/routes')
def routes():
    if 'stravaid' not in session:
        return redirect("/", code=302)

    # if ('dversion' not in session):
    session["dversion"] = random.random()
    print("dversion:" + str(session['dversion']))

    jsource = "/static/routes_" + str(session['stravaid']) + ".js?v=" + str(session['dversion'])
    if (gcloud):
        jsource = "https://storage.googleapis.com/straview.appspot.com" + jsource
    return render_template('poly.html', jsource = jsource)


@app.route('/login')
def login():
    print ("port:" + str(port))
    return redirect(redirecturl, code=302)

@app.route('/login2')
def login2():
    # should get: http://localhost:5001/login2?state=&code=f6ce444973ea0d26bee2b9a11f212099ff76dd8b&scope=read,activity:read_all
    code = request.args.get('code')
    scope = request.args.get('scope')
    if ("activity:read_all" in scope):
        response = requests.post(
                            url = 'https://www.strava.com/oauth/token',
                            data = {
                                    'client_id': client_id,
                                    'client_secret': client_secret,
                                    'code': code,
                                    'grant_type': 'authorization_code'
                                    }
                        )

        #Save json response as a variable
        strava_tokens = response.json()
        if ('message' in strava_tokens):
             print(str(strava_tokens['message']))
             return 'ERROR' + str(strava_tokens)

        print(str(strava_tokens))
        stravaid = strava_tokens['athlete']['id']
        session['stravaid'] = strava_tokens['athlete']['id']
        session['firstname'] = strava_tokens['athlete']['firstname']

        # Need to obfuscate this at a later date
        # Save tokens to file
        putStringFile(json.dumps(strava_tokens), 'data/strava_tokens_' + str(stravaid) + '.json', False)
        resp = make_response(render_template('login2.html', name =session['firstname'] ))
        resp.set_cookie('known', '1', expires=datetime.datetime.now() + datetime.timedelta(days=1000))
        return resp
#        return str(data + session['stravaid'])    
    else:
        return 'Require read_all to be checked to use this app - sorry! Go back and and fix if you wish to continue.'


@app.route('/delete')
def delete():
    if 'stravaid' not in session:
        return "NOT PERMITTED"

    f = 'data/strava_tokens_' + str(session["stravaid"]) + '.json'
    if os.path.exists(f): 
        os.remove(f)
    f = "static/routes_" + str(session["stravaid"]) +".js"
    if os.path.exists(f): 
        os.remove(f)
    resp = make_response(render_template('delete.html'))
    resp.set_cookie('known', '0', expires=0)
    session.pop('stravaid',None)
    session.pop('firstname',None)
    return resp


@app.route('/refresh')
def refresh():
    if 'firstname' not in session:
        return '*** must be logged in via strava'

    maxactivity = 200
    ## Get the tokens from file to connect to Strava
    strava_tokens = get_strava_tokens()
    ## If access_token has expired then use the refresh_token to get the new access_token
    if strava_tokens['expires_at'] < time.time():
    #Make Strava auth API call with current refresh token
        response = requests.post(
                            url = 'https://www.strava.com/oauth/token',
                            data = {
                                    'client_id': client_id,
                                    'client_secret': client_secret,
                                    'grant_type': 'refresh_token',
                                    'refresh_token': strava_tokens['refresh_token']
                                    }
                        )

    #Save response as json in new variable
        strava_tokens = response.json()
    # Save new tokens to file
        putStringFile(json.dumps(strava_tokens), 'data/strava_tokens_' + str(stravaid) + '.json', False)
    #Loop through all activities
    page = 1
    activity = 0
    url = "https://www.strava.com/api/v3/activities"
    print ("before access tokens")
    access_token = strava_tokens['access_token']
    print ("after access tokens")
    ## Create the dataframe ready for the API call to store your activity data
    
    script = "var encodedRoutes = [\n"

    # array to use in the display table
    displayActs = []
    displayFields = [{"title": "activity number"}]
    # Display v. raw internal
    rawFields = [
                    [ "Activity",   "name"],
                    [ "Date",       "start_date_local"],
                    [ "Type",        "type"],
                    [ "Av mph", "average_speed"],
                    [ "Miles", "distance"],
                    [ "Elev Gain (m)", "total_elevation_gain"],
                    [ "Moving Hrs", "moving_time"],
                    [ "Elapse Hrs", "elapsed_time"],
                    [ "With", "athlete_count"]]
    for f in rawFields:
        displayFields.append({"title": f[0]})

    while True:        
        # get page of activities from Strava
        r = requests.get(url + '?access_token=' + access_token + '&per_page=200' + '&page=' + str(page))
        r = r.json()
    # if no results then exit loop
        if (not r):
            break
        
        # otherwise add new data to dataframe
        
        for act in r:
            # print ("\n$$$$$$$$$ x,len(r)" + str(x) + "," + str(len(r)))
            # print ("\n" + str(r[x]))
            polyline = act["map"]["summary_polyline"]
            # print ("\n***POLY:" + polyline)
            if (polyline):
                popup = str(act['start_date_local']) + "<br/>" + str(act['name'])
                script += '["' + popup + '","' + polyline.replace('\\','\\\\') + '"],\n'
                # First column is hidden field of the sequential activity number
                disp = [str(activity)]
                for field in rawFields:

                    # Do conversions for readability
                    val = act[field[1]]
                    if (field[1] == "name"):
                        val = "<a href='https://www.strava.com/activities/" + str(act['id']) + "' target=_blank><img src='/static/strava_icon.svg' style='height:16px' alt='view in strava'/></a>"  + val
                    if (field[1] == "distance"):
                        val = "{:.1f}".format(float(val)* 0.000621371192)
                    if (field[1] == "start_date_local"):
                        val = val[:10]
                    if ("Hrs" in field[0]):
                        val = "{:.1f}".format(float(val)/ 3600)
                    if ("mph" in field[0]):
                        val = "{:.1f}".format(float(val)* 3600 * 0.000621371192)
                    if ("With" in field[0]):
                        val = str(int(val) - 1)

                    disp.append(val)
                displayActs.append(disp)



    #ONLY NEED to get the specific journey if we need the accurate polyline
            # r2 = requests.get("https://www.strava.com/api/v3/activities/"  + str(r[x]['id']) + '?access_token=' + access_token + "&include_all_efforts=true")
            # if (r2 and r2.json()["map"] and "summary_polyline" in r2.json()["map"]):
            #     # print ("\nMAP:" + str(r[x]['id']) + " " + str(r2.json()["map"]))  
            #     polyline = r2.json()["map"]["summary_polyline"]
            #     # polyline = r2.json()["map"]["polyline"]
            #     if (polyline):
            #         popup = str(r[x]['start_date_local']) + "<br/>" + str(r[x]['name'])
            #         fscript.write('["' + popup + '","' + polyline.replace('\\','\\\\') + '"],\n')

                activity += 1
                if (activity >= maxactivity):
                    break
            if (activity >= maxactivity):
                break
        if (activity >= maxactivity):
            break
    # increment page
        page += 1

    script += '["",""]\n]\n'

    script += '\ndisplayFields = '
    script += json.dumps(displayFields)

    script += '\ndisplayActs = '
    script += json.dumps(displayActs)
    print ("about to write", script)
    putStringFile (script,"static/routes_" + str(session["stravaid"]) +".js", True)

    session['dversion'] = random.random()
    return redirect("/routes", code=302)


if __name__ == '__main__':
    random.seed()
    app.run(debug=debug, host='0.0.0.0', port=port)
    # Assume we are in Google Cloud, otherwise run with parameter
    