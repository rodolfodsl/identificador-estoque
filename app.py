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

CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534".strip()
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25".strip()

# MOTOR DOBRADO (ViT-B-16 tem muito mais precisão para detalhes finos)
@st.cache_resource
def carregar_modelo():
    return SentenceTransformer('clip-ViT-B-16')

modelo = carregar_modelo()

def baixar_imagem(url, token=None):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        if token and 'bling.com.br' in url:
            headers['Authorization'] = f'Bearer {token}'
            
        url_limpa = str(url).split(',')[0].split('|')[0].strip()
        if url_limpa.startswith("//"):
            url_limpa = "https:" + url_limpa
            
        resp = requests.get(url_limpa, headers=headers, timeout=6)
        if resp.status_code == 200:
            return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        pass
    return None

if 'access_token' not in st.session_state:
    st.warning("⚠️ Conexão com a API do Bling necessária para extrair as fotos.")
    st.markdown("""
    1. Gere um novo link de convite no painel do Bling.
    2. Copie o **código** gerado na barra de endereços (`code=...`).
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
    
    arquivo_csv = st.file_uploader("Arraste o arquivo .csv do Bling", type=['csv'])
    
    if arquivo_csv:
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        
        if 'ID' in df.columns and 'Descrição' in df.columns:
            st.markdown("### 🔍 Qual lote você quer fotografar agora?")
            termo = st.text_input("Digite uma palavra (Ex: RELÓGIO, BOLSA):")
            
            if termo:
                df_filtrado = df[df['Descrição'].str.contains(termo.upper(), na=False)].copy()
                st.write(f"Encontrados **{len(df_filtrado)}** produtos da categoria '{termo.upper()}'.")
                
                if len(df_filtrado) > 0:
                    if st.button(f"Carregar IA para esses {len(df_filtrado)} itens"):
                        st.session_state['catalogo_ativo'] = df_filtrado.to_dict('records')
                        if 'catalogo_com_ia' in st.session_state:
                            del st.session_state['catalogo_com_ia']
                            
                    if 'catalogo_ativo' in st.session_state and 'catalogo_com_ia' not in st.session_state:
                        st.write("⏳ **Baixando fotos de alta resolução do Bling...**")
                        barra = st.progress(0)
                        
                        produtos_finais = []
                        headers_api = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
                        
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
                                    imagens = dados.get('midia', {}).get('imagens', {})
                                    
                                    if isinstance(imagens, dict):
                                        ext = imagens.get('externas', [])
                                        int_img = imagens.get('internas', [])
                                        if ext and len(ext) > 0:
                                            link_foto = ext[0].get('link')
                                        elif int_img and len(int_img) > 0:
                                            link_foto = int_img[0].get('linkMiniatura') or int_img[0].get('link')
                                    elif isinstance(imagens, list) and len(imagens) > 0:
                                        link_foto = imagens[0].get('link') or imagens[0].get('url')
                            except Exception:
                                pass
                                
                            emb = None
                            if link_foto:
                                img_obj = baixar_imagem(link_foto, token)
                                if img_obj:
                                    emb = modelo.encode(img_obj)
                                    
                            if emb is not None:
                                produtos_finais.append({
                                    'nome': nome_prod,
                                    'codigo_barras': cod_prod,
                                    'link': link_foto,
                                    'embedding': emb
                                })
                                
                            time.sleep(0.35)
                            barra.progress(int(((i + 1) / total) * 100))
                            
                        st.session_state['catalogo_com_ia'] = pd.DataFrame(produtos_finais)
                        st.rerun()
                        
                    elif 'catalogo_com_ia' in st.session_state:
                        catalogo = st.session_state['catalogo_com_ia']
                        
                        if len(catalogo) > 0:
                            st.success(f"✅ Inteligência Artificial de Alta Precisão ligada!")
                            
                            if st.button("Limpar Lote / Trocar de Categoria"):
                                del st.session_state['catalogo_ativo']
                                del st.session_state['catalogo_com_ia']
                                st.rerun()
                                
                            st.divider()
                            st.markdown("### 📸 Dicas para cravar o acerto:")
                            st.markdown("- **Esconda a etiqueta branca:** Ela confunde muito a IA. Dobre-a para trás.\n- **Fundo Limpo:** Coloque o relógio sobre uma folha de papel branca (sulfite) em vez da mesa de madeira.")
                            
                            foto_tirada = st.camera_input("Fotografe a peça bem centralizada:")
                            
                            if foto_tirada:
                                img_original = Image.open(foto_tirada).convert('RGB')
                                
                                # ZOOM DIGITAL: Corta 40% das bordas (onde fica a mesa) e foca 60% no centro
                                largura, altura = img_original.size
                                tamanho = min(largura, altura) * 0.6
                                esq = (largura - tamanho) / 2
                                topo = (altura - tamanho) / 2
                                dir = (largura + tamanho) / 2
                                fundo = (altura + tamanho) / 2
                                
                                img_foco = img_original.crop((esq, topo, dir, fundo))
                                
                                st.write("👀 **O que a IA está analisando (Foco):**")
                                st.image(img_foco, width=200)
                                
                                emb_busca = modelo.encode(img_foco)
                                
                                scores = []
                                for emb_prod in catalogo['embedding']:
                                    sim = util.cos_sim(emb_busca, emb_prod).item()
                                    scores.append(sim)
                                    
                                catalogo['similaridade'] = scores
                                # Agora mostra o TOP 5 para garantir
                                top_5 = catalogo.sort_values(by='similaridade', ascending=False).head(5)
                                
                                st.subheader("Itens Correspondentes:")
                                for idx, item in top_5.iterrows():
                                    st.markdown(f"### 🏷️ {item['nome']}")
                                    col_1, col_2 = st.columns([1, 2])
                                    with col_1:
                                        img_ref = baixar_imagem(item['link'], token)
                                        if img_ref:
                                            st.image(img_ref, width=150)
                                    with col_2:
                                        st.write(f"**SKU:** `{item['codigo_barras']}`")
                                        st.write(f"**Precisão da IA:** {item['similaridade']:.1%}")
                                        if item['similaridade'] >= 0.70:
                                            st.success("✅ **ALTA PROBABILIDADE**")
                                    st.divider()
                        else:
                            st.error("Nenhuma foto foi encontrada no Bling para este lote.")
