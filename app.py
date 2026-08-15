import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer, util

st.set_page_config(page_title="Identificador de Estoque", layout="centered")
st.title("👜 Identificador Visual de Estoque")

# 1. Carregar modelo visual
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

# 2. Carregar produtos da planilha online
@st.cache_data(ttl=1800)
def carregar_catalogo(url_planilha):
    todos_produtos = []
    
    # Baixar a planilha para memória
    resp = requests.get(url_planilha)
    excel_file = BytesIO(resp.content)
    
    # Lê todas as abas disponíveis
    xls = pd.ExcelFile(excel_file)
    
    for nome_aba in xls.sheet_names:
        # Foca nas abas de produtos e categorias
        if any(chave in nome_aba.upper() for chave in ['BIJUTERIA', 'BOLSA', 'PRODUTO', 'ESTOQUE']):
            try:
                df = pd.read_excel(excel_file, sheet_name=nome_aba)
                
                # Procura as colunas certas independente da linha do cabeçalho
                col_prod = [c for c in df.columns if 'PRODUTO' in str(c).upper()]
                col_cod = [c for c in df.columns if 'BARRA' in str(c).upper() or 'ETIQUE' in str(c).upper()]
                col_link = [c for c in df.columns if 'LINK' in str(c).upper() or 'FOTO' in str(c).upper()]
                
                if col_prod and col_link:
                    c_p = col_prod[0]
                    c_l = col_link[0]
                    c_c = col_cod[0] if col_cod else None
                    
                    df_validos = df[[c_p, c_l]].dropna()
                    for idx, row in df.iterrows():
                        link_val = str(row[c_l]).strip()
                        prod_val = str(row[c_p]).strip()
                        cod_val = str(row[c_c]).replace('.0', '').strip() if c_c else "Sem Código"
                        
                        if link_val.startswith("http") and prod_val and prod_val.lower() != 'nan':
                            todos_produtos.append({
                                'nome': prod_val,
                                'codigo_barras': cod_val,
                                'link': link_val,
                                'categoria': nome_aba
                            })
            except Exception:
                continue

    df_final = pd.DataFrame(todos_produtos)
    
    if len(df_final) == 0:
        return df_final

    # Gerar os embeddings das imagens
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

# URL Direta da Planilha
URL_ONEDRIVE = "https://onedrive.live.com/download?cid=abe99b31d34a8839&resid=d34a8839-9b31-20e9-80ab-710500000000"

with st.spinner("Lendo planilha e indexando fotos do estoque..."):
    catalogo = carregar_catalogo(URL_ONEDRIVE)

st.success(f"{len(catalogo)} produtos cadastrados e sincronizados com sucesso!")

# 3. Câmera
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
                st.image(img_ref, width=150, caption="Foto da Planilha")
                
        with col_dados:
            st.write(f"**Código de Barras:** `{item['codigo_barras']}`")
            st.write(f"**Aba / Categoria:** {item['categoria']}")
            st.write(f"**Similaridade:** {item['similaridade']:.1%}")
            
            if item['similaridade'] >= 0.75:
                st.success("✅ **ALTA PROBABILIDADE (REPOSIÇÃO)**")
            else:
                st.warning("⚠️ Conferir detalhes visuais antes de cadastrar.")
        st.divider()
