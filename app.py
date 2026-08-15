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

@st.cache_data(ttl=600)
def carregar_produtos_bling_v3():
    # Insira aqui o novo Client ID e Client Secret gerados ao recriar o app:
    CLIENT_ID = "7cb24f904b59341c3bd3dd9037f1b8f772a56b6e".strip()
    CLIENT_SECRET = "32cb95f1c1ba40f2acbceff3c6ada40cb378859192780ace48c92b64489b".strip()
    
    # Novo código de autorização:
    AUTHORIZATION_CODE = "ae9d2d0016f22207a50ac6d7cfecb4960649c3d6".strip()
    
    token_url = "https://www.bling.com.br/Api/v3/oauth/token"
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "grant_type": "authorization_code",
        "code": AUTHORIZATION_CODE
    }
    
    try:
        resp_token = requests.post(token_url, headers=headers, data=data)
        token_data = resp_token.json()
        
        if "access_token" not in token_data:
            st.error(f"Erro ao obter token do Bling: {token_data}")
            return pd.DataFrame()
            
        access_token = token_data["access_token"]
    except Exception as e:
        st.error(f"Erro na requisição de token: {e}")
        return pd.DataFrame()

    todos_produtos = []
    pagina = 1
    
    headers_api = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    while True:
        url_produtos = f"https://www.bling.com.br/Api/v3/produtos?pagina={pagina}&limite=100"
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

with st.spinner("Sincronizando produtos e imagens do Bling v3..."):
    catalogo = carregar_produtos_bling_v3()

if len(catalogo) > 0:
    st.success(f"✅ Sincronizado com sucesso! {len(catalogo)} produtos carregados do Bling v3.")
    
    st.write("---")
    foto_tirada = st.camera_input("Fotografe a peça para identificar:")

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
                    st.image(img_ref, width=150, caption="Foto do Bling")
                    
            with col_dados:
                st.write(f"**Código / SKU:** `{item['codigo_barras']}`")
                st.write(f"**Fonte:** {item['categoria']}")
                st.write(f"**Precisão da IA:** {item['similaridade']:.1%}")
                
                if item['similaridade'] >= 0.75:
                    st.success("✅ **ALTA PROBABILIDADE**")
                else:
                    st.warning("⚠️ Conferir detalhes visuais.")
            st.divider()
else:
    st.warning("Nenhum produto com imagem foi retornado pela API v3. Verifique se os produtos cadastrados no Bling possuem fotos anexadas.")
