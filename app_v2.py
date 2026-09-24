from pathlib import Path
import streamlit as st
from engine import GOALS, SCOPES, DATA, load_catalog, visible_apps, recommend, contact_link, valid_url, data_question, readiness_message, parse_customer_request

st.set_page_config(page_title='Hertzler | AI Solution Finder', page_icon='🔎', layout='centered')
try:
    catalog = load_catalog(Path(__file__).with_name('app_catalog.json'))
except (ValueError, OSError, TypeError, KeyError) as exc:
    st.error('The app catalog could not be loaded. Please contact the site administrator.')
    st.caption(str(exc))
    st.stop()

st.markdown('<span style="color:#087f8c;font-weight:700;letter-spacing:2px">HERTZLER SYSTEMS</span>', unsafe_allow_html=True)
st.title('Find your AI quality solution')
st.write('Tell us what you want to improve. Explore a free demo, then talk with Hertzler about making it fit your process.')
if catalog['preview_mode']:
    st.warning('Preview — all ten app descriptions and demo links are configured, along with the Hertzler contact page.')
st.caption('Guided recommendations based on your selections. No AI model is used by this finder.')

s = st.session_state
for key, value in {'step': 0, 'answers': {}}.items():
    if key not in s:
        s[key] = value

def reset():
    s.step = 0
    s.answers = {}
    for key in ('goal_pick', 'scope_pick', 'data_pick'):
        s.pop(key, None)

def advance(key, value):
    if key == 'goal' and s.answers.get('goal') != value:
        s.answers = {}
    s.answers[key] = value
    s.step += 1
    st.rerun()

def contact_button(app=None, key='contact'):
    link = contact_link(catalog, app)
    if link:
        st.link_button('Contact Hertzler for customization', link, use_container_width=True)
    else:
        st.button('Contact link coming soon', disabled=True, key=key, use_container_width=True)

def app_card(app, prefix):
    with st.container(border=True):
        st.subheader(app['name'])
        st.write(app['summary'])
        if catalog['preview_mode'] and app.get('review_status') == 'source_missing':
            st.caption('Draft description — current source file not supplied.')
        if app.get('demo_instructions'):
            st.markdown('**Getting started in the demo**')
            st.write(app['demo_instructions'])
        st.markdown('**Why explore this app**')
        st.write(app['why'])
        with st.expander('Data, results, and customization'):
            for label, field in [('Data to discuss', 'required_data'), ('What it provides', 'outputs'), ('Potential customization', 'customizations')]:
                st.markdown('**' + label + '**')
                for item in app[field]:
                    st.write('• ' + item)
            st.markdown('**Limitations**')
            st.write(app['limitations'])
        left, right = st.columns(2)
        with left:
            if valid_url(app.get('demo_url', '')):
                st.link_button('Try free demo ↗', app['demo_url'], type='primary', use_container_width=True)
            else:
                st.button('Demo link coming soon', key=prefix + app['id'] + '_demo', disabled=True, use_container_width=True)
        with right:
            contact_button(app, prefix + app['id'] + '_contact')

find_tab, text_tab, browse_tab, help_tab = st.tabs(['Find my solution', 'Describe my problem', 'Explore all apps', 'How it works'])
with find_tab:
    st.progress(min(s.step, 3) / 3)
    if s.step == 0:
        st.subheader('1 · What would you like to improve?')
        options = list(GOALS)
        selected = st.radio('Choose your main goal', options, index=options.index(s.answers.get('goal', 'predict')), format_func=GOALS.get, key='goal_pick')
        if st.button('Continue →', type='primary', key='next_goal'):
            advance('goal', selected)
    elif s.step == 1:
        goal = s.answers['goal']
        st.caption('Your goal: ' + GOALS[goal])
        if goal == 'unusual':
            st.subheader('2 · What would you like to investigate?')
            options = list(SCOPES)
            selected = st.radio('Choose the closest description', options, index=options.index(s.answers.get('scope', 'unsure')), format_func=SCOPES.get, key='scope_pick')
            if st.button('Continue →', type='primary', key='next_scope'):
                advance('scope', selected)
        else:
            s.answers['scope'] = 'unsure'
            s.step = 2
            st.rerun()
    elif s.step == 2:
        st.subheader(data_question(s.answers['goal']))
        st.caption('You can explore the demos before deciding whether to customize an app.')
        options = list(DATA)
        selected = st.radio('Your data today', options, index=options.index(s.answers.get('data', 'unsure')), format_func=(lambda x: {'yes': 'Yes', 'no': 'No', 'unsure': 'I am not sure'}[x]) if s.answers['goal'] == 'database' else DATA.get, key='data_pick')
        if st.button('Show my options →', type='primary', key='next_data'):
            advance('data', selected)
    else:
        goal = s.answers['goal']
        scope = s.answers.get('scope', 'unsure')
        matches = recommend(catalog, goal, scope)
        st.subheader('Options for your process')
        st.caption('Your goal: ' + GOALS[goal])
        st.info(readiness_message(goal, s.answers['data']))
        if matches:
            if len(matches) > 1:
                st.write('More than one app may fit. Compare their purposes and data requirements below.')
            for app in matches:
                app_card(app, 'result_')
        else:
            st.info('We do not have a confirmed catalog match for this selection. Explore the apps or contact Hertzler to discuss your requirement.')
            contact_button(key='no_match_contact')
        summary = '\n'.join(['Hertzler AI Solution Finder', 'Goal: ' + GOALS[goal], 'Scope: ' + SCOPES[scope], 'Readiness question: ' + data_question(goal), 'Answer: ' + s.answers['data'], 'Apps to discuss: ' + (', '.join(a['name'] for a in matches) or 'Custom consultation'), '', 'Customization needs: '])
        st.download_button('Download my discussion summary', summary, file_name='hertzler_discussion_summary.txt', mime='text/plain')
        st.caption('No inquiry has been sent. Use the contact link to submit a request to Hertzler.')
    c1, c2 = st.columns(2)
    with c1:
        if s.step > 0 and st.button('← Back', key='back'):
            s.step = 0 if s.step == 2 and s.answers.get('goal') != 'unusual' else max(0, s.step - 1)
            st.rerun()
    with c2:
        st.button('Start over', on_click=reset, key='restart')
with text_tab:
    st.subheader('What would you like help with?')
    st.write('Describe your goal, or name an app you want to explore.')
    st.caption('Examples: How often should we inspect? • Our SQL Server is slow • Find unusual batches • Generate a certificate of analysis')
    with st.form('problem_form'):
        problem = st.text_area('Your problem or goal', max_chars=2000,
                               placeholder='We want to find unusual batches and reduce repeated operator entries.',
                               key='problem_input')
        submitted = st.form_submit_button('Find matching apps', type='primary')
    if submitted:
        s['submitted_problem'] = problem.strip()
    if 'submitted_problem' in s:
        query = s['submitted_problem']
        if not query:
            st.info('Enter a problem or goal, or use the guided questions in Find my solution.')
        else:
            st.markdown('**Your submitted request**')
            st.text(query)
            text_matches = parse_customer_request(catalog, query)
            st.caption('Matches use supported words and phrases. Complex wording or spelling errors may need rephrasing; these are options to explore, not confirmed suitability.')
            if text_matches:
                if len(text_matches) > 1:
                    st.info('Several apps match your wording. Compare the options below, or use the guided questions to narrow your goal.')
                for match in text_matches:
                    st.write('Matched wording: ' + ', '.join(match['matched_phrases']))
                    app_card(match['app'], 'text_')
            else:
                st.info('No clear match found. Try a more specific description, use Find my solution, or contact Hertzler about your requirement.')
                contact_button(key='text_no_match_contact')
            text_summary = '\n'.join(['Hertzler AI Solution Finder', 'Customer request: ' + query,
                                      'Apps to discuss: ' + (', '.join(m['app']['name'] for m in text_matches) or 'Custom consultation'),
                                      '', 'Customization needs: '])
            st.download_button('Download this request summary', text_summary,
                               file_name='hertzler_request_summary.txt', mime='text/plain', key='text_summary')
            st.caption('No inquiry has been sent. Open the contact page when you want to submit a request.')
with browse_tab:
    apps = visible_apps(catalog)
    if not apps:
        st.info('Our app catalog is being prepared. Please check back soon.')
    for app in apps:
        app_card(app, 'browse_')
with help_tab:
    st.markdown('''**1. Find an option**  
Choose your goal and answer a few questions, or describe your need in the Describe my problem tab.

**2. Try the free demo**  
Demo links open a separate app in a new tab. Review the instructions inside each demo.

**3. Make it fit your process**  
If the app looks useful, contact Hertzler to discuss your data, requirements, and customization.

**How are recommendations selected?**  
The finder matches your selected goal and, where relevant, the type of data you want to investigate to approved catalog rules. The Describe my problem tab also matches supported words and phrases in typed requests. It uses no AI model and may miss unfamiliar wording.

**Does a recommendation confirm the app will work for us?**  
No. It identifies an option to explore. Data suitability and customization feasibility require further assessment.

**Will this send an inquiry automatically?**  
No. You choose when to open the contact page and submit a request.''')
