import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer, util

st.set_page_config(page_title="Identificador de Estoque", layout="centered")
st.title("👜 Identificador Visual de Estoque")

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
def carregar_dados(url_planilha, api_key_bling):
    todos_produtos = []
    
    # 1. Carregar do Google Planilhas (Se houver link)
    if url_planilha:
        try:
            abas_dict = pd.read_excel(url_planilha, engine='openpyxl', sheet_name=None)
            for nome_aba, df in abas_dict.items():
                if any(chave in nome_aba.upper() for chave in ['BIJUTERIA', 'BOLSA', 'PRODUTO', 'ESTOQUE']):
                    col_prod = [c for c in df.columns if 'PRODUTO' in str(c).upper()]
                    col_cod = [c for c in df.columns if 'BARRA' in str(c).upper() or 'ETIQUE' in str(c).upper()]
                    col_link = [c for c in df.columns if 'LINK' in str(c).upper() or 'FOTO' in str(c).upper()]
                    
                    if col_prod and col_link:
                        c_p = col_prod[0]
                        c_l = col_link[0]
                        c_c = col_cod[0] if col_cod else None
                        
                        for idx, row in df.iterrows():
                            link_val = str(row[c_l]).strip()
                            prod_val = str(row[c_p]).strip()
                            cod_val = str(row[c_c]).replace('.0', '').strip() if c_c else "Sem Código"
                            
                            if link_val.startswith("http") and prod_val and prod_val.lower() != 'nan':
                                todos_produtos.append({
                                    'nome': prod_val,
                                    'codigo_barras': cod_val,
                                    'link': link_val,
                                    'categoria': f"Planilha: {nome_aba}"
                                })
        except Exception:
            pass

    # 2. Carregar do ERP Bling (Se houver chave)
    if api_key_bling:
        pagina = 1
        while True:
            # Puxa 100 produtos por página com a imagem habilitada
            url = f"https://bling.com.br/Api/v2/produtos/page={pagina}/json/?apikey={api_key_bling}&imagem=S"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    break
                
                dados = resp.json()
                if 'retorno' in dados and 'produtos' in dados['retorno']:
                    for item in dados['retorno']['produtos']:
                        p = item['produto']
                        nome = p.get('descricao', '')
                        codigo = p.get('codigo', 'Sem Código')
                        
                        link_img = None
                        if 'imagem' in p and len(p['imagem']) > 0:
                            link_img = p['imagem'][0].get('link')
                            
                        if nome and link_img:
                            todos_produtos.append({
                                'nome': nome,
                                'codigo_barras': codigo,
                                'link': link_img,
                                'categoria': 'ERP Bling'
                            })
                    pagina += 1
                else:
                    break
            except Exception:
                break

    df_final = pd.DataFrame(todos_produtos)
    if len(df_final) == 0:
        return df_final

    # Remove produtos duplicados (caso você tenha o mesmo item na planilha e no Bling)
    df_final = df_final.drop_duplicates(subset=['nome'])

    # 3. Gerar Inteligência Visual
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

# ==========================================
# COLE SEUS LINKS E CHAVES AQUI EMBAIXO
# ==========================================
URL_PLANILHA = "" # Se for usar o Google Sheets depois, cole o link aqui
API_KEY_BLING = "cd96a6839920db48210337e3a59a568e0409a1d0dd8d857f7a2e57b624996c87c2f7888e"
# ==========================================

with st.spinner("Sincronizando banco de dados do Bling e da Planilha... Isso pode levar um minuto na primeira vez..."):
    catalogo = carregar_dados(URL_PLANILHA, API_KEY_BLING)

if len(catalogo) > 0:
    st.success(f"✅ Automação 100% ativa! {len(catalogo)} produtos identificados no estoque.")
    
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
                    st.image(img_ref, width=150, caption="Foto do Cadastro")
                    
            with col_dados:
                st.write(f"**Código:** `{item['codigo_barras']}`")
                st.write(f"**Fonte:** {item['categoria']}")
                st.write(f"**Precisão da IA:** {item['similaridade']:.1%}")
                
                if item['similaridade'] >= 0.75:
                    st.success("✅ **ALTA PROBABILIDADE**")
                else:
                    st.warning("⚠️ Conferir detalhes visuais.")
            st.divider()
else:
    st.warning("Aguardando leitura de produtos... Verifique sua chave do Bling.")
