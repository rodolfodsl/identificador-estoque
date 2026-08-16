import streamlit as st
import pandas as pd
import requests
import base64
import time
from io import BytesIO
from PIL import Image
import torch
import torchvision.models as models

st.set_page_config(page_title="Identificador Visual", layout="centered")
st.title("👜 Identificador de Estoque (Motor PRO)")

CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534".strip()
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25".strip()

# --- NOVO CÉREBRO: RESNET-50 (Padrão Ouro para Similaridade Visual) ---
@st.cache_resource
def carregar_modelo():
    weights = models.ResNet50_Weights.DEFAULT
    resnet = models.resnet50(weights=weights)
    # Remove a última camada para pegar apenas o "Raio-X" da textura (2048 características)
    resnet = torch.nn.Sequential(*list(resnet.children())[:-1])
    resnet.eval()
    preprocesso = weights.transforms()
    return resnet, preprocesso

modelo, preprocesso = carregar_modelo()

def extrair_caracteristicas(img):
    try:
        img_rgb = img.convert('RGB')
        tensor = preprocesso(img_rgb).unsqueeze(0)
        with torch.no_grad():
            features = modelo(tensor)
        return features.flatten()
    except Exception:
        return None

def baixar_imagem(url, token=None):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        if token and 'bling.com.br' in url:
            headers['Authorization'] = f'Bearer {token}'
            
        url_limpa = str(url).split(',')[0].split('|')[0].strip()
        if url_limpa.startswith("//"):
            url_limpa = "https:" + url_limpa
            
        resp = requests.get(url_limpa, headers=headers, timeout=5)
        if resp.status_code == 200:
            return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        pass
    return None

if 'access_token' not in st.session_state:
    st.warning("⚠️ Conexão com a API do Bling necessária.")
    auth_code_input = st.text_input("Cole o CÓDIGO de autorização gerado no Bling aqui:")
    
    if st.button("🔗 Conectar ao Bling"):
        if auth_code_input:
            with st.spinner("Autenticando..."):
                token_url = "https://api.bling.com.br/Api/v3/oauth/token"
                credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                headers = {"Authorization": f"Basic {encoded_credentials}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "1.0"}
                data = {"grant_type": "authorization_code", "code": auth_code_input.strip()}
                try:
                    resp_token = requests.post(token_url, headers=headers, data=data)
                    token_data = resp_token.json()
                    if "access_token" in token_data:
                        st.session_state['access_token'] = token_data["access_token"]
                        st.success("Conectado! Carregando...")
                        st.rerun()
                    else:
                        st.error("Código expirado. Gere um novo no Bling e tente de novo.")
                except Exception as e:
                    st.error(f"Erro: {e}")
else:
    token = st.session_state['access_token']
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.success("✅ Conectado ao Bling.")
    with col2:
        if st.button("Desconectar"):
            del st.session_state['access_token']
            st.rerun()
            
    st.divider()
    arquivo_csv = st.file_uploader("Arraste o arquivo .csv do Bling", type=['csv'])
    
    if arquivo_csv:
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        if 'ID' in df.columns and 'Descrição' in df.columns:
            termo = st.text_input("Qual categoria você quer ler? (Ex: RELÓGIO):")
            
            if termo:
                df_filtrado = df[df['Descrição'].str.contains(termo.upper(), na=False)].copy()
                st.write(f"Encontrados **{len(df_filtrado)}** itens.")
                
                if len(df_filtrado) > 0:
                    if st.button(f"Memorizar detalhes visuais das {len(df_filtrado)} peças"):
                        st.session_state['catalogo_ativo'] = df_filtrado.to_dict('records')
                        if 'catalogo_com_ia' in st.session_state:
                            del st.session_state['catalogo_com_ia']
                            
                    if 'catalogo_ativo' in st.session_state and 'catalogo_com_ia' not in st.session_state:
                        st.write("⏳ **Extraindo texturas e formatos (pode levar 1-2 minutos)...**")
                        barra = st.progress(0)
                        
                        produtos_finais = []
                        headers_api = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
                        total = len(st.session_state['catalogo_ativo'])
                        
                        for i, row in enumerate(st.session_state['catalogo_ativo']):
                            link_foto = None
                            try:
                                resp = requests.get(f"https://api.bling.com.br/Api/v3/produtos/{row['ID']}", headers=headers_api, timeout=5)
                                if resp.status_code == 200:
                                    imagens = resp.json().get('data', {}).get('midia', {}).get('imagens', {})
                                    if isinstance(imagens, dict):
                                        ext = imagens.get('externas', [])
                                        int_img = imagens.get('internas', [])
                                        if ext: link_foto = ext[0].get('link')
                                        elif int_img: link_foto = int_img[0].get('linkMiniatura') or int_img[0].get('link')
                                    elif isinstance(imagens, list) and len(imagens) > 0:
                                        link_foto = imagens[0].get('link') or imagens[0].get('url')
                            except:
                                pass
                                
                            emb = None
                            if link_foto:
                                img_obj = baixar_imagem(link_foto, token)
                                if img_obj:
                                    emb = extrair_caracteristicas(img_obj)
                                    
                            if emb is not None:
                                produtos_finais.append({'nome': row['Descrição'], 'codigo_barras': row.get('Código', 'Sem Código'), 'link': link_foto, 'embedding': emb})
                                
                            time.sleep(0.35)
                            barra.progress(int(((i + 1) / total) * 100))
                            
                        st.session_state['catalogo_com_ia'] = produtos_finais
                        st.rerun()
                        
                    elif 'catalogo_com_ia' in st.session_state:
                        catalogo = st.session_state['catalogo_com_ia']
                        if len(catalogo) > 0:
                            st.success(f"✅ Inteligência Visual Ativa! {len(catalogo)} peças analisadas.")
                            
                            st.divider()
                            
                            st.markdown("### 📸 DICA DE OURO PARA O 1º LUGAR:")
                            st.markdown("*Dobre a etiqueta para não aparecer na foto e posicione o relógio sobre uma folha branca lisa.*")
                            
                            foto_tirada = st.camera_input("Fotografe a peça:")
                            
                            # O SLIDER MÁGICO: Ajuda a ignorar a mesa
                            zoom = st.slider("Zoom da Lente (Use para cortar a mesa e focar na peça)", min_value=1.0, max_value=3.0, value=1.5, step=0.1)
                            
                            if foto_tirada:
                                img_original = Image.open(foto_tirada).convert('RGB')
                                
                                # APLICA O ZOOM DIGITAL
                                largura, altura = img_original.size
                                tamanho = min(largura, altura) / zoom
                                esq = (largura - tamanho) / 2
                                topo = (altura - tamanho) / 2
                                dir = (largura + tamanho) / 2
                                fundo = (altura + tamanho) / 2
                                
                                img_foco = img_original.crop((esq, topo, dir, fundo))
                                
                                st.write("👀 **Visão pura da Inteligência Artificial:**")
                                st.image(img_foco, width=150)
                                
                                emb_busca = extrair_caracteristicas(img_foco)
                                
                                if emb_busca is not None:
                                    resultados = []
                                    for item in catalogo:
                                        # Calcula a similaridade matemática do novo cérebro
                                        sim = torch.nn.functional.cosine_similarity(emb_busca.unsqueeze(0), item['embedding'].unsqueeze(0)).item()
                                        resultados.append({'nome': item['nome'], 'codigo_barras': item['codigo_barras'], 'link': item['link'], 'similaridade': sim})
                                        
                                    top_5 = sorted(resultados, key=lambda x: x['similaridade'], reverse=True)[:5]
                                    
                                    st.subheader("Melhores Correspondências:")
                                    for item in top_5:
                                        st.markdown(f"### 🏷️ {item['nome']}")
                                        col_1, col_2 = st.columns([1, 2])
                                        with col_1:
                                            img_ref = baixar_imagem(item['link'], token)
                                            if img_ref: st.image(img_ref, width=150)
                                        with col_2:
                                            st.write(f"**SKU:** `{item['codigo_barras']}`")
                                            st.write(f"**Confiabilidade Visual:** {item['similaridade']:.1%}")
                                            if item['similaridade'] >= 0.85:
                                                st.success("✅ **ALTA PROBABILIDADE**")
                                        st.divider()
                        else:
                            st.error("Nenhuma foto encontrada para esta categoria.")
                            if st.button("Tentar Novamente"):
                                del st.session_state['catalogo_ativo']
                                del st.session_state['catalogo_com_ia']
                                st.rerun()
