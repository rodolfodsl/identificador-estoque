import streamlit as st
import pandas as pd
import requests
import base64
import time
from io import BytesIO
from PIL import Image
from sentence_transformers import SentenceTransformer, util

st.set_page_config(page_title="Identificador Visual", layout="centered")
st.title("👜 Identificador Visual de Estoque")

# --- CREDENCIAIS FIXAS DO BLING ---
CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534".strip()
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25".strip()

@st.cache_resource
def carregar_modelo():
    return SentenceTransformer('clip-ViT-B-32')

modelo = carregar_modelo()

def baixar_imagem(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url_limpa = str(url).split(',')[0].split('|')[0].strip()
        if url_limpa.startswith("//"):
            url_limpa = "https:" + url_limpa
        resp = requests.get(url_limpa, headers=headers, timeout=5)
        return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        return None

# --- TELA DE AUTENTICAÇÃO ---
if 'access_token' not in st.session_state:
    st.warning("⚠️ Conexão com a API do Bling necessária para extrair as fotos.")
    st.markdown("""
    1. Gere um novo link de convite no painel do Bling.
    2. Autorize o aplicativo.
    3. Copie o **código** gerado na barra de endereços (o que vem depois de `code=`).
    """)
    
    auth_code_input = st.text_input("Cole o CÓDIGO de autorização aqui:")
    
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
                        st.error("Código expirado. Gere um novo no Bling e tente de novo.")
                except Exception as e:
                    st.error(f"Erro de comunicação: {e}")

# --- SISTEMA HÍBRIDO ---
else:
    token = st.session_state['access_token']
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.success("✅ API do Bling Conectada!")
    with col2:
        if st.button("Desconectar"):
            del st.session_state['access_token']
            st.rerun()
            
    st.divider()
    
    st.info("💡 Envie a sua planilha CSV do Bling (aquela de 10 mil itens) para usarmos como Mapa.")
    arquivo_csv = st.file_uploader("Arraste o arquivo .csv aqui", type=['csv'])
    
    if arquivo_csv:
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        
        if 'ID' in df.columns and 'Descrição' in df.columns:
            st.write(f"📊 **Mapa do Estoque lido:** {len(df)} produtos cadastrados.")
            
            st.markdown("### 🔍 Qual lote você quer fotografar agora?")
            termo = st.text_input("Digite uma palavra (Ex: CINTO, BOLSA, UNHA, RELÓGIO):")
            
            if termo:
                df_filtrado = df[df['Descrição'].str.contains(termo.upper(), na=False)].copy()
                st.write(f"Encontrados **{len(df_filtrado)}** produtos da categoria '{termo.upper()}'.")
                
                if len(df_filtrado) > 0:
                    if st.button(f"Carregar IA para esses {len(df_filtrado)} itens"):
                        st.session_state['catalogo_ativo'] = df_filtrado.to_dict('records')
                        if 'catalogo_com_ia' in st.session_state:
                            del st.session_state['catalogo_com_ia']
                            
                    if 'catalogo_ativo' in st.session_state and 'catalogo_com_ia' not in st.session_state:
                        st.write("⏳ **Baixando as fotos do servidor do Bling...**")
                        barra = st.progress(0)
                        
                        produtos_finais = []
                        headers_api = {
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/json"
                        }
                        
                        total = len(st.session_state['catalogo_ativo'])
                        for i, row in enumerate(st.session_state['catalogo_ativo']):
                            id_prod = row['ID']
                            nome_prod = row['Descrição']
                            cod_prod = row.get('Código', 'Sem Código')
                            
                            link_foto = None
                            try:
                                resp = requests.get(f"https://api.bling.com.br/Api/v3/produtos/{id_prod}", headers=headers_api, timeout=5)
                                if resp.status_code == 200:
                                    dados = resp.json().get('data', {})
                                    imagens = dados.get('midia', {}).get('imagens', [])
                                    if len(imagens) > 0:
                                        link_foto = imagens[0].get('link') or imagens[0].get('url')
                            except Exception:
                                pass
                                
                            emb = None
                            if link_foto:
                                img_obj = baixar_imagem(link_foto)
                                if img_obj:
                                    emb = modelo.encode(img_obj)
                                    
                            if emb is not None:
                                produtos_finais.append({
                                    'nome': nome_prod,
                                    'codigo_barras': cod_prod,
                                    'link': link_foto,
                                    'embedding': emb
                                })
                                
                            time.sleep(0.35) # Proteção para o Bling não bloquear
                            barra.progress(int(((i + 1) / total) * 100))
                            
                        st.session_state['catalogo_com_ia'] = pd.DataFrame(produtos_finais)
                        st.rerun()
                        
                    # --- CÂMERA MÁGICA ---
                    elif 'catalogo_com_ia' in st.session_state:
                        catalogo = st.session_state['catalogo_com_ia']
                        
                        if len(catalogo) > 0:
                            st.success(f"✅ Inteligência Artificial ligada! {len(catalogo)} peças prontas.")
                            
                            if st.button("Limpar Lote / Trocar de Categoria"):
                                del st.session_state['catalogo_ativo']
                                del st.session_state['catalogo_com_ia']
                                st.rerun()
                                
                            st.divider()
                            foto_tirada = st.camera_input("📸 Fotografe a peça:")
                            
                            if foto_tirada:
                                img_busca = Image.open(foto_tirada).convert('RGB')
                                emb_busca = modelo.encode(img_busca)
                                
                                scores = []
                                for emb_prod in catalogo['embedding']:
                                    sim = util.cos_sim(emb_busca, emb_prod).item()
                                    scores.append(sim)
                                    
                                catalogo['similaridade'] = scores
                                top_3 = catalogo.sort_values(by='similaridade', ascending=False).head(3)
                                
                                st.subheader("Itens Correspondentes:")
                                for idx, item in top_3.iterrows():
                                    st.markdown(f"### 🏷️ {item['nome']}")
                                    col_1, col_2 = st.columns([1, 2])
                                    with col_1:
                                        img_ref = baixar_imagem(item['link'])
                                        if img_ref:
                                            st.image(img_ref, width=150)
                                    with col_2:
                                        st.write(f"**SKU:** `{item['codigo_barras']}`")
                                        st.write(f"**Precisão da IA:** {item['similaridade']:.1%}")
                                        if item['similaridade'] >= 0.75:
                                            st.success("✅ **ALTA PROBABILIDADE**")
                                    st.divider()
                        else:
                            st.error("O Bling não retornou nenhuma foto para essa categoria. Tente outra.")
                            if st.button("Tentar Novamente"):
                                del st.session_state['catalogo_ativo']
                                del st.session_state['catalogo_com_ia']
                                st.rerun()
        else:
            st.error("Planilha inválida. Certifique-se de que é a exportação do Bling.")
