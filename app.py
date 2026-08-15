import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from PIL import Image
from sentence_transformers import SentenceTransformer, util

st.set_page_config(page_title="Identificador Visual", layout="centered")
st.title("👜 Identificador Visual de Estoque")

@st.cache_resource
def carregar_modelo():
    return SentenceTransformer('clip-ViT-B-32')

modelo = carregar_modelo()

def baixar_imagem(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        # Se houver vários links no Bling, pega apenas a primeira foto
        url_limpa = str(url).split('|')[0].split(',')[0].strip()
        if not url_limpa.startswith("http"):
            return None
        resp = requests.get(url_limpa, headers=headers, timeout=5)
        return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        return None

st.info("💡 **Como usar:** Arraste o arquivo CSV exportado do Bling para a caixa abaixo.")

# Aceitando o arquivo CSV
arquivo_csv = st.file_uploader("Arraste a Planilha Exportada (.csv)", type=['csv'])

if arquivo_csv:
    # Lê o CSV padrão do Bling (separado por ponto e vírgula)
    df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
    
    # Identifica as colunas oficiais dinamicamente
    col_nome = next((c for c in df.columns if 'nome' in str(c).lower() or 'descrição' in str(c).lower()), None)
    col_cod = next((c for c in df.columns if 'código' in str(c).lower() or 'sku' in str(c).lower()), None)
    col_img = next((c for c in df.columns if 'imagem' in str(c).lower() or 'url' in str(c).lower()), None)
    
    if col_nome and col_img:
        # Pega apenas as peças que possuem link de foto na planilha
        df_valido = df.dropna(subset=[col_img]).copy()
        
        # Trava de segurança para memória do servidor
        if len(df_valido) > 500:
            st.warning(f"Sua planilha possui {len(df_valido)} peças com foto. Para a nuvem não travar, a IA vai aprender apenas as primeiras 500.")
            df_valido = df_valido.head(500)
            
        if len(df_valido) > 0:
            # Processamento Visual
            if 'processado' not in st.session_state:
                st.write("⏳ **Memorizando as fotos das peças... (Isso acontece apenas uma vez)**")
                barra = st.progress(0)
                
                embeddings = []
                for i, row in df_valido.iterrows():
                    img = baixar_imagem(row[col_img])
                    if img:
                        embeddings.append(modelo.encode(img))
                    else:
                        embeddings.append(None)
                    
                    # Atualiza a barrinha verde
                    progresso = int(((i + 1) / len(df_valido)) * 100)
                    barra.progress(min(progresso, 100))
                    
                df_valido['embedding'] = embeddings
                st.session_state['catalogo'] = df_valido.dropna(subset=['embedding'])
                st.session_state['processado'] = True
                st.rerun()
            
            else:
                catalogo = st.session_state['catalogo']
                st.success(f"✅ {len(catalogo)} peças carregadas na memória e prontas para leitura!")
                
                if st.button("Trocar Planilha / Limpar"):
                    del st.session_state['processado']
                    st.rerun()
                
                st.divider()
                
                # Câmera Mágica
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
                    
                    st.subheader("Peças Correspondentes:")
                    for idx, item in top_3.iterrows():
                        st.markdown(f"### 🏷️ {item[col_nome]}")
                        col_1, col_2 = st.columns([1, 2])
                        with col_1:
                            img_ref = baixar_imagem(item[col_img])
                            if img_ref:
                                st.image(img_ref, width=150)
                        with col_2:
                            st.write(f"**Código/SKU:** `{item[col_cod] if col_cod else 'Sem código'}`")
                            st.write(f"**Precisão da IA:** {item['similaridade']:.1%}")
                            
                            if item['similaridade'] >= 0.75:
                                st.success("✅ **ALTA PROBABILIDADE**")
                            else:
                                st.warning("⚠️ Conferir detalhes visuais.")
                        st.divider()
        else:
            st.error("Nenhuma foto válida encontrada na coluna da planilha.")
    else:
        st.error("Não consegui achar as colunas 'Descrição' e 'URL Imagens' na planilha do Bling.")
