import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer, util

st.set_page_config(page_title="Identificador de Estoque", layout="centered")
st.title("👜 Identificador Visual de Estoque")

# 1. Carregar o modelo visual de IA (gratuito)
@st.cache_resource
def carregar_modelo():
    return SentenceTransformer('clip-ViT-B-32')

modelo = carregar_modelo()

# Função auxiliar para extrair a foto real do link do Google Fotos
def baixar_imagem_google_fotos(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        if "photos.app.goo.gl" in url:
            soup = BeautifulSoup(resp.text, 'html.parser')
            meta = soup.find("meta", property="og:image")
            if meta:
                img_url = meta["content"]
                resp = requests.get(img_url, timeout=5)
        return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        return None

# 2. Carregar e indexar os produtos da planilha online
@st.cache_data(ttl=3600)
def carregar_catalogo(url_planilha):
    abas = ['BIJUTERIAS_ACESSÓRIOS', 'BOLSAS_MOCHILAS']
    todos_produtos = []
    
    for aba in abas:
        try:
            df = pd.read_excel(url_planilha, sheet_name=aba)
            df_limpo = df[['PRODUTO', 'Nº cod. Barra P/ ETIQUE', 'LINK']].dropna(subset=['LINK', 'PRODUTO'])
            
            for _, row in df_limpo.iterrows():
                link = str(row['LINK']).strip()
                if link.startswith("http"):
                    todos_produtos.append({
                        'nome': str(row['PRODUTO']).strip(),
                        'codigo_barras': str(row['Nº cod. Barra P/ ETIQUE']).replace('.0', ''),
                        'link': link,
                        'categoria': aba
                    })
        except Exception:
            continue
            
    df_final = pd.DataFrame(todos_produtos)
    
    embeddings = []
    for _, row in df_final.iterrows():
        img = baixar_imagem_google_fotos(row['link'])
        if img:
            emb = modelo.encode(img)
            embeddings.append(emb)
        else:
            embeddings.append(None)
            
    df_final['embedding'] = embeddings
    return df_final.dropna(subset=['embedding'])

# Link direto para a sua planilha compartilhada do OneDrive
URL_ONEDRIVE = "https://1drv.ms/x/c/abe99b31d34a8839/UQA5iErTMZvpIICrcQUAAAAAABvXjqK3EYeqBtE?download=1"

with st.spinner("Sincronizando produtos com a planilha do OneDrive..."):
    catalogo = carregar_catalogo(URL_ONEDRIVE)

st.success(f"{len(catalogo)} produtos cadastrados e sincronizados!")

# 3. Câmera para identificar a mercadoria
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
    
    st.subheader("Itens Mais Prováveis no Estoque:")
    
    for idx, item in top_3.iterrows():
        st.markdown(f"### 🏷️ {item['nome']}")
        col_img, col_dados = st.columns([1, 2])
        
        with col_img:
            img_ref = baixar_imagem_google_fotos(item['link'])
            if img_ref:
                st.image(img_ref, width=150, caption="Foto da Planilha")
                
        with col_dados:
            st.write(f"**Código de Barras:** `{item['codigo_barras']}`")
            st.write(f"**Categoria / Aba:** {item['categoria']}")
            st.write(f"**Certeza da IA:** {item['similaridade']:.1%}")
            
            if item['similaridade'] >= 0.80:
                st.success("✅ **ALTA PROBABILIDADE DE SER ESTE PRODUTO (REPOSIÇÃO)**")
            else:
                st.warning("⚠️ Verifique os detalhes visuais antes de dar entrada.")
        st.divider()
