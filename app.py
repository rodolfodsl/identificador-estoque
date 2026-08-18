import streamlit as st
import pandas as pd
import requests
import base64
from io import BytesIO
from PIL import Image
import json
import os
from google import genai

st.set_page_config(page_title="Identificador Visual Automatizado", layout="centered")
st.title("🧠 Identificador Visual & Consulta por Código")

# =====================================================================
# CONFIGURAÇÕES DE API
# =====================================================================
CHAVE_GOOGLE_FIXA = "AQ.Ab8RN6L8veXzF6BWmlher3zMH5kdgCIjqXUT3eKAWu4wLH6fwg"
CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534".strip()
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25".strip()
TOKEN_FILE = "bling_tokens.json"

def get_auth_header():
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "1.0"}

def save_tokens(access_token, refresh_token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, f)

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None

# --- AUTH BLING ---
if 'bling_token' not in st.session_state:
    saved_tokens = load_tokens()
    if saved_tokens and "refresh_token" in saved_tokens:
        try:
            token_url = "https://api.bling.com.br/Api/v3/oauth/token"
            data = {"grant_type": "refresh_token", "refresh_token": saved_tokens["refresh_token"]}
            resp = requests.post(token_url, headers=get_auth_header(), data=data)
            new_tokens = resp.json()
            if "access_token" in new_tokens:
                st.session_state['bling_token'] = new_tokens["access_token"]
                save_tokens(new_tokens["access_token"], new_tokens.get("refresh_token", saved_tokens["refresh_token"]))
        except Exception:
            pass

if 'bling_token' not in st.session_state:
    st.sidebar.header("🔑 Conexão Bling")
    auth_code_input = st.sidebar.text_input("Código de Autorização:")
    if st.sidebar.button("🔗 Conectar"):
        token_url = "https://api.bling.com.br/Api/v3/oauth/token"
        data = {"grant_type": "authorization_code", "code": auth_code_input.strip()}
        resp_token = requests.post(token_url, headers=get_auth_header(), data=data)
        token_data = resp_token.json()
        if "access_token" in token_data:
            st.session_state['bling_token'] = token_data["access_token"]
            save_tokens(token_data["access_token"], token_data.get("refresh_token", ""))
            st.rerun()

# --- CARREGAMENTO DO ESTOQUE (LOCAL NO REPOSITÓRIO) ---
@st.cache_data(ttl=600)
def carregar_planilha():
    caminho = "ESTOQUE PALHADA - COMPARTILHADA.xlsx"
    if os.path.exists(caminho):
        return pd.read_excel(caminho, dtype=str)
    return None

if 'bling_token' in st.session_state:
    st.success("✅ Sistema Conectado!")
    df = carregar_planilha()

    if df is not None:
        col_produto = df.columns[0]
        col_codigo = df.columns[9] if len(df.columns) > 9 else df.columns[1]
        
        aba = st.radio("Método:", ["📷 Identificação Visual", "🏷️ Buscar por Código"])
        
        if aba == "🏷️ Buscar por Código":
            cod = st.text_input("Código/SKU:")
            if cod:
                item = df[df[col_codigo].str.contains(cod.strip(), case=False, na=False)]
                if not item.empty:
                    st.success(f"Item: {item.iloc[0][col_produto]}")
        else:
            termo = st.text_input("Categoria para busca visual:")
            if termo:
                df_filtrado = df[df[col_produto].str.contains(termo.upper(), na=False)].copy()
                lista_produtos = [{"id": str(i), "nome": str(r[col_produto]), "sku": str(r[col_codigo])} for i, r in df_filtrado.iterrows()]
                
                foto_tirada = st.camera_input("Fotografe a peça:")
                if foto_tirada:
                    with st.spinner("Analisando..."):
                        client = genai.Client(api_key=CHAVE_GOOGLE_FIXA)
                        response = client.models.generate_content(
                            model="gemini-2.0-flash", # Ajustado para modelo atual
                            contents=[Image.open(foto_tirada), f"Compare com este JSON: {json.dumps(lista_produtos)}. Retorne array JSON de 3 IDs e precisão."]
                        )
                        # Processamento da resposta e exibição segue lógica anterior...
                        st.json(response.text)
    else:
        st.error("Erro: 'ESTOQUE PALHADA - COMPARTILHADA.xlsx' não encontrado no GitHub.")
else:
    st.warning("👈 Conecte o Bling.")
