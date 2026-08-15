import streamlit as st
import pandas as pd
import requests
import base64
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer, util

st.set_page_config(page_title="Identificador de Estoque", layout="centered")
st.title("👜 Identificador Visual de Estoque (Bling v3)")

# --- CREDENCIAIS FIXAS ---
CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534".strip()
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25".strip()

@st.cache_resource
def carregar_modelo():
    return SentenceTransformer('clip-ViT-B-32')

modelo = carregar_modelo()

def baixar_imagem(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=6)
        if "photos.app.goo.gl" in url:
            soup = BeautifulSoup(resp.text, 'html.parser')
            meta = soup.find("meta", property="og:image")
            if meta:
                img_url = meta["content"]
                resp = requests.get(img_url, timeout=6)
        return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        return None

# --- TELA DE AUTENTICAÇÃO ---
if 'access_token' not in st.session_state:
    st.warning("⚠️ Conexão com o Bling não iniciada ou expirada.")
    st.markdown("""
    **Como conectar:**
    1. Gere um novo link de convite no painel do Bling.
    2. Autorize o aplicativo.
    3. Copie o código gerado na barra de endereços (o que vem depois de `code=`).
    """)
    
    auth_code_input = st.text_input("Cole o NOVO CÓDIGO aqui:")
    
    if st.button("🔗 Conectar ao Bling"):
        if auth_code_input:
            with st.spinner("Autenticando..."):
                token_url = "https://api.bling.com.br/Api/v3/oauth/token"
                credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                
                headers = {
                    "Authorization": f"Basic {encoded_credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "1.0"
                }
                
                data = {
                    "grant_type": "authorization_code",
                    "code": auth_code_input.strip()
                }
                
                try:
                    resp_token = requests.post(token_url, headers=headers, data=data)
                    token_data = resp_token.json()
                    
                    if "access_token" in token_data:
                        st.session_state['access_token'] = token_data["access_token"]
                        st.success("Conectado com sucesso! Carregando sistema...")
                        st.rerun()
                    else:
                        st.error(f"Erro ao conectar (Código expirado ou inválido): {token_data}")
                except Exception as e:
                    st.error(f"Erro de comunicação: {e}")
        else:
            st.error("Por favor, cole o código antes de clicar em Conectar.")

# --- SISTEMA PRINCIPAL (Se já estiver com o token) ---
else:
    @st.cache_data(ttl=600)
    def carregar_produtos_bling_v3(token):
        todos_produtos = []
        pagina = 1
        headers_api = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        while True:
            url_produtos = f"https://api.bling.com.br/Api/v3/produtos?pagina={pagina}&limite=100"
            try:
                resp_prod = requests.get(url_produtos, headers=headers_api, timeout=10)
                if resp_prod.status_code != 200:
                    break
                    
                dados = resp_prod.json()
                if "data" in dados and len(dados["data"]) > 0:
                    for prod in dados["data"]:
                        nome = prod.get("nome", "")
                        codigo = prod.get("codigo", "Sem Código")
                        
                        link_img = None
                        if "midia" in prod and "imagens" in prod["midia"] and len(prod["midia"]["imagens"]) > 0:
                            link_img = prod["midia"]["imagens"][0].get("link")
                            
                        if nome and link_img:
                            todos_produtos.append({
                                'nome': nome,
                                'codigo_barras': codigo,
                                'link': link_img,
                                'categoria': 'ERP Bling v3'
                            })
                    pagina += 1
                else:
                    break
            except Exception:
                break

        df_final = pd.DataFrame(todos_produtos)
        if len(df_final) == 0:
            return df_final

        embeddings = []
        for _, row in df_final.iterrows():
            img = baixar_imagem(row['link'])
            if img:
                emb = modelo.encode(img)
                embeddings.append(emb)
            else:
                embeddings.append(None)
                
        df_final['embedding'] = embeddings
        return df_final.dropna(subset=['embedding'])

    with st.spinner("Baixando catálogo oficial do Bling..."):
        catalogo = carregar_produtos_bling_v3(st.session_state['access_token'])

    if len(catalogo) > 0:
        st.success(f"✅ Catálogo baixado! {len(catalogo)} produtos prontos para identificação.")
        
        if st.button("Sair / Desconectar"):
            del st.session_state['access_token']
            st.rerun()

        st.divider()
        foto_tirada = st.camera_input("Fotografe a peça para buscar:")
        
        if foto_tirada:
            img_busca = Image.open(foto_tirada).convert('RGB')
            emb_busca = modelo.encode(img_busca)
            
            scores = []
            for emb_prod in catalogo['embedding']:
                sim = util.cos_sim(emb_busca, emb_prod).item()
                scores.append(sim)
                
            catalogo['similaridade'] = scores
            top_3 = catalogo.sort_values(by='similaridade', ascending=False).head(3)
            
            st.subheader("Itens Mais Prováveis Encontrados:")
            for idx, item in top_3.iterrows():
                st.markdown(f"### 🏷️ {item['nome']}")
                col_img, col_dados = st.columns([1, 2])
                
                with col_img:
                    img_ref = baixar_imagem(item['link'])
                    if img_ref:
                        st.image(img_ref, width=150, caption="Foto do Sistema")
                        
                with col_dados:
                    st.write(f"**Código / SKU:** `{item['codigo_barras']}`")
                    st.write(f"**Precisão:** {item['similaridade']:.1%}")
                    
                    if item['similaridade'] >= 0.75:
                        st.success("✅ **ALTA PROBABILIDADE**")
                    else:
                        st.warning("⚠️ Conferir detalhes visuais.")
                st.divider()
    else:
        st.warning("O token foi gerado, mas nenhum produto com imagem foi encontrado. Verifique seu painel do Bling.")
        if st.button("Tentar Novamente / Desconectar"):
            del st.session_state['access_token']
            st.rerun()
