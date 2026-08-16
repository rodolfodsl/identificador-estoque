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
        url_limpa = str(url).split(',')[0].split('|')[0].strip()
        
        if url_limpa.startswith("//"):
            url_limpa = "https:" + url_limpa
            
        if not url_limpa.startswith("http"):
            return None
            
        resp = requests.get(url_limpa, headers=headers, timeout=5)
        return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        return None

st.info("💡 **Como usar:** Baixe sua Planilha do Google (como .xlsx ou .csv) e arraste para a caixa abaixo. Certifique-se de que os links das fotos estão públicos!")

arquivo = st.file_uploader("Arraste a sua Planilha Arrumada (.xlsx ou .csv)", type=['xlsx', 'csv'])

if arquivo:
    if arquivo.name.endswith('.csv'):
        df = pd.read_csv(arquivo, sep=None, engine='python', dtype=str)
    else:
        df = pd.read_excel(arquivo, engine='openpyxl', dtype=str)
    
    col_nome = next((c for c in df.columns if any(x in str(c).lower() for x in ['nome', 'descrição', 'produto', 'peça'])), None)
    col_cod = next((c for c in df.columns if any(x in str(c).lower() for x in ['código', 'sku', 'ref'])), None)
    col_img = next((c for c in df.columns if any(x in str(c).lower() for x in ['imagem', 'url', 'link', 'foto'])), None)
    
    if col_nome and col_img:
        df_valido = df.dropna(subset=[col_img]).copy()
        
        if len(df_valido) > 500:
            st.warning(f"Sua planilha tem {len(df_valido)} fotos. A IA vai carregar as primeiras 500 para evitar travamentos.")
            df_valido = df_valido.head(500)
            
        if len(df_valido) > 0:
            # TRAVA DE SEGURANÇA: Verifica se a memória está corrompida e força o reprocessamento
            precisa_processar = 'processado' not in st.session_state or 'catalogo' not in st.session_state or 'embedding' not in st.session_state['catalogo'].columns

            if precisa_processar:
                st.write("⏳ **Baixando as fotos da sua planilha e ensinando a Inteligência Artificial...**")
                barra = st.progress(0)
                
                embeddings = []
                for i, row in df_valido.iterrows():
                    img = baixar_imagem(row[col_img])
                    if img:
                        embeddings.append(modelo.encode(img))
                    else:
                        embeddings.append(None)
                    
                    progresso = int(((i + 1) / len(df_valido)) * 100)
                    barra.progress(min(progresso, 100))
                    
                df_valido['embedding'] = embeddings
                st.session_state['catalogo'] = df_valido.dropna(subset=['embedding'])
                st.session_state['processado'] = True
                st.rerun()
            
            else:
                catalogo = st.session_state['catalogo']
                st.success(f"✅ SUCESSO! {len(catalogo)} peças da sua planilha estão prontas para leitura.")
                
                if st.button("Carregar Nova Planilha"):
                    # Agora o botão limpa tudo corretamente
                    del st.session_state['processado']
                    if 'catalogo' in st.session_state:
                        del st.session_state['catalogo']
                    st.rerun()
                
                st.divider()
                
                foto_tirada = st.camera_input("📸 Fotografe a peça para buscar no estoque:")
                if foto_tirada:
                    img_busca = Image.open(foto_tirada).convert('RGB')
                    emb_busca = modelo.encode(img_busca)
                    
                    scores = []
                    for emb_prod in catalogo['embedding']:
                        sim = util.cos_sim(emb_busca, emb_prod).item()
                        scores.append(sim)
                        
                    catalogo['similaridade'] = scores
                    top_3 = catalogo.sort_values(by='similaridade', ascending=False).head(3)
                    
                    st.subheader("Peças Encontradas na sua Planilha:")
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
            st.error("A planilha foi carregada, mas não encontrei nenhum link válido preenchido na coluna de fotos.")
    else:
        st.error("Sua planilha precisa ter pelo menos uma coluna chamada 'Nome' (ou Descrição) e uma coluna chamada 'Link' (ou URL/Foto).")
