import os
import requests
import streamlit as st
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load env file if it exists
load_dotenv()

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "whalasahib@gmail.com")
APP_URL = os.getenv("APP_URL", "http://inventra.website").rstrip('/')
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

# Google OAuth endpoints
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"

def is_google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

def get_google_auth_url() -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": APP_URL,
        "response_type": "code",
        "scope": "openid email profile",
        "state": "oauth_state",
        "prompt": "select_account"
    }
    return f"{AUTH_URI}?{urlencode(params)}"

def authenticate_google_code(code: str) -> dict | None:
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": APP_URL,
        "grant_type": "authorization_code"
    }
    try:
        res = requests.post(TOKEN_URI, data=data, timeout=10)
        if res.status_code != 200:
            return None
        tokens = res.json()
        access_token = tokens.get("access_token")
        if not access_token:
            return None
        
        # Fetch user info
        headers = {"Authorization": f"Bearer {access_token}"}
        user_res = requests.get(USERINFO_URI, headers=headers, timeout=10)
        if user_res.status_code == 200:
            return user_res.json()
    except Exception as e:
        st.error(f"Error during Google authentication: {e}")
    return None

def check_auth() -> bool:
    """
    Renders login screen if not authenticated.
    Returns True if user is logged in and is the owner.
    """
    if "authenticated_email" not in st.session_state:
        st.session_state.authenticated_email = None

    if st.session_state.authenticated_email:
        # Check if they are the owner
        if st.session_state.authenticated_email.strip().lower() == OWNER_EMAIL.strip().lower():
            return True
        else:
            st.error(f"Access Denied: User '{st.session_state.authenticated_email}' is not the owner of this project.")
            if st.button("Sign Out / Retry", key="retry_signout"):
                st.session_state.authenticated_email = None
                st.query_params.clear()
                st.rerun()
            return False

    # Handle incoming OAuth redirect code
    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        # Clear code from parameters to keep URL clean
        st.query_params.clear()
        
        with st.spinner("Authenticating with Google..."):
            userinfo = authenticate_google_code(code)
            if userinfo and "email" in userinfo:
                st.session_state.authenticated_email = userinfo["email"]
                st.rerun()
            else:
                st.error("Authentication failed or email could not be retrieved from Google.")

    # Show Login UI
    st.markdown("""
        <style>
        .login-box {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 3rem;
            background: rgba(18, 18, 29, 0.85);
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
            text-align: center;
            margin-top: 4rem;
        }
        .login-logo {
            font-size: 2.2rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            background: linear-gradient(90deg, #60A5FA, #34D399, #FBBF24);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: 0.05em;
        }
        .login-desc {
            color: #9CA3AF;
            font-size: 0.95rem;
            margin-bottom: 2rem;
        }
        .google-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            background-color: #ffffff;
            color: #1F2937;
            font-size: 1rem;
            font-weight: 600;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            border: 1px solid #E5E7EB;
            cursor: pointer;
            text-decoration: none;
            width: 100%;
            transition: all 0.2s ease;
        }
        .google-btn:hover {
            background-color: #F9FAFB;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        </style>
    """, unsafe_allow_html=True)

    # Let's put layout in columns to center the login container
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        st.markdown(
            f"""
            <div class="login-box">
                <div class="login-logo">INVENTRA COMMAND</div>
                <div class="login-desc">Trading Bot Management Control Center</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        st.write("")
        
        if is_google_configured():
            st.markdown(
                f'<a href="{get_google_auth_url()}" target="_self" style="text-decoration: none;">'
                '<div class="google-btn">'
                '<svg style="margin-right: 10px; width: 18px; height: 18px;" viewBox="0 0 24 24">'
                '<path fill="#EA4335" d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.137 4.114-3.466 0-6.277-2.81-6.277-6.277 0-3.466 2.81-6.277 6.277-6.277 1.564 0 2.973.57 4.073 1.503l3.078-3.078C19.123 2.047 15.932 1 12.24 1 6.033 1 1 6.033 1 12.24s5.033 11.24 11.24 11.24c6.452 0 11.24-4.526 11.24-11.24 0-.75-.078-1.48-.22-1.955H12.24z"/>'
                '</svg>'
                'Sign In with Google'
                '</div>'
                '</a>',
                unsafe_allow_html=True
            )
        else:
            st.warning("⚠️ Google OAuth is not configured in `.env`. Falling back to Dev Simulated Sign-In.")
            dev_email = st.text_input("Simulated Google Email Address:", value="whalasahib@gmail.com")
            if st.button("Proceed with Google Simulation", use_container_width=True):
                st.session_state.authenticated_email = dev_email
                st.success(f"Logged in as {dev_email}!")
                st.rerun()

    return False

def sign_out():
    st.session_state.authenticated_email = None
    st.query_params.clear()
    st.rerun()
