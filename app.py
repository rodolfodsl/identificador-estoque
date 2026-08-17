import streamlit as st
import pandas as pd
import requests
import base64
from io import BytesIO
from PIL import Image
import json
import os
from google import genai

st.set_page_config(page_title="Identificador Visual Automatizado", layout="centered")
st.title("🧠 Identificador Visual & Consulta por Código")

# =====================================================================
# CHAVE DO GOOGLE FIXA E LINK DIRETO DO EXCEL NO ONEDRIVE
# =====================================================================
CHAVE_GOOGLE_FIXA = "AQ.Ab8RN6L8veXzF6BWmlher3zMH5kdgCIjqXUT3eKAWu4wLH6fwg"
LINK_ONEDRIVE = "https://onedrive.live.com/personal/abe99b31d34a8839/_layouts/15/download.aspx?UniqueId=d34a8839%2D9b31%2D20e9%2D80ab%2D710500000000"

# --- CREDENCIAIS FIXAS DO BLING (PARA AS FOTOS) ---
CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534".strip()
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25".strip()

TOKEN_FILE = "bling_tokens.json"

def get_auth_header():
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "1.0"}

def save_tokens(access_token, refresh_token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, f)

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None

if 'bling_token' not in st.session_state:
    saved_tokens = load_tokens()
    if saved_tokens and "refresh_token" in saved_tokens:
        try:
            token_url = "https://api.bling.com.br/Api/v3/oauth/token"
            data = {"grant_type": "refresh_token", "refresh_token": saved_tokens["refresh_token"]}
            resp = requests.post(token_url, headers=get_auth_header(), data=data)
            new_tokens = resp.json()
            if "access_token" in new_tokens:
                st.session_state['bling_token'] = new_tokens["access_token"]
                save_tokens(new_tokens["access_token"], new_tokens.get("refresh_token", saved_tokens["refresh_token"]))
        except Exception:
            pass

if 'bling_token' not in st.session_state:
    st.sidebar.header("🔑 Primeira Conexão Bling")
    auth_code_input = st.sidebar.text_input("Código de Autorização do Bling:")
    if st.sidebar.button("🔗 Conectar e Salvar Sessão"):
        if auth_code_input:
            with st.spinner("Autenticando..."):
                token_url = "https://api.bling.com.br/Api/v3/oauth/token"
                data = {"grant_type": "authorization_code", "code": auth_code_input.strip()}
                try:
                    resp_token = requests.post(token_url, headers=get_auth_header(), data=data)
                    token_data = resp_token.json()
                    if "access_token" in token_data:
                        st.session_state['bling_token'] = token_data["access_token"]
                        save_tokens(token_data["access_token"], token_data.get("refresh_token", ""))
                        st.sidebar.success("Conectado com sucesso!")
                        st.rerun()
                    else:
                        st.sidebar.error("Código do Bling expirado.")
                except Exception as e:
                    st.sidebar.error(f"Erro: {e}")

# --- FUNÇÃO PARA BAIXAR FOTO DO BLING ---
def baixar_foto_bling_unica(id_produto, token):
    headers_api = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        resp = requests.get(f"https://api.bling.com.br/Api/v3/produtos/{id_produto}", headers=headers_api, timeout=5)
        if resp.status_code == 200:
            imagens = resp.json().get('data', {}).get('midia', {}).get('imagens', {})
            link_foto = None
            if isinstance(imagens, dict):
                ext = imagens.get('externas', [])
                int_img = imagens.get('internas', [])
                if ext: link_foto = ext[0].get('link')
                elif int_img: link_foto = int_img[0].get('linkMiniatura') or int_img[0].get('link')
            elif isinstance(imagens, list) and len(imagens) > 0:
                link_foto = imagens[0].get('link') or imagens[0].get('url')
                
            if link_foto:
                headers = {'User-Agent': 'Mozilla/5.0'}
                if 'bling.com.br' in link_foto: headers['Authorization'] = f'Bearer {token}'
                url_limpa = str(link_foto).split(',')[0].split('|')[0].strip()
                if url_limpa.startswith("//"): url_limpa = "https:" + url_limpa
                resp_img = requests.get(url_limpa, headers=headers, timeout=5)
                if resp_img.status_code == 200:
                    return Image.open(BytesIO(resp_img.content)).convert('RGB')
    except Exception:
        pass
    return None

# SÓ CARREGA O APP SE O BLING ESTIVER CONECTADO
if 'bling_token' in st.session_state:
    st.success("✅ Sistema Conectado ao OneDrive e Bling!")
    
    # CARREGAMENTO AUTOMÁTICO DA PLANILHA DO ONEDRIVE
    @st.cache_data(ttl=600)
    def carregar_planilha_nuvem():
        try:
            resp = requests.get(LINK_ONEDRIVE)
            if resp.status_code == 200:
                df = pd.read_excel(BytesIO(resp.content), dtype=str)
                return df
        except Exception as e:
            st.error(f"Erro ao baixar planilha do OneDrive: {e}")
        return None

    with st.spinner("🔄 Sincronizando catálogo do OneDrive..."):
        df = carregar_planilha_nuvem()

    if df is not None:
        col_produto = df.columns[0] # Coluna A
        col_codigo = df.columns[9] if len(df.columns) > 9 else df.columns[1] # Coluna J
        
        st.divider()
        aba_escolha = st.radio("Como você quer consultar o item?", ["📷 Identificação Visual por Câmera", "🏷️ Buscar por Código de Barras / SKU"])
        st.divider()
        
        if aba_escolha == "🏷️ Buscar por Código de Barras / SKU":
            st.info("Digite ou escaneie o código de barras impresso na etiqueta.")
            codigo_digitado = st.text_input("Código de Barras / SKU:")
            
            if codigo_digitado:
                item_encontrado = df[df[col_codigo].str.contains(codigo_digitado.strip(), case=False, na=False)]
                
                if not item_encontrado.empty:
                    st.success("Item encontrado no estoque!")
                    for _, row in item_encontrado.iterrows():
                        nome_prod = row[col_produto]
                        cod_prod = row[col_codigo]
                        st.markdown(f"### Produto: {nome_prod}")
                        st.write(f"**Código de Barras / SKU:** `{cod_prod}`")
                        st.divider()
                else:
                    st.warning("Nenhum produto encontrado com este código na planilha do OneDrive.")

        else:
            termo = st.text_input("Qual categoria vamos buscar? (Ex: TORNOZELEIRA, KIT, RELÓGIO):")
            
            if termo:
                df_filtrado = df[df[col_produto].str.contains(termo.upper(), na=False)].copy()
                st.write(f"Encontrados **{len(df_filtrado)}** itens no catálogo.")
                
                lista_produtos = []
                for index, row in df_filtrado.iterrows():
                    lista_produtos.append({
                        "id": str(index),
                        "nome": str(row[col_produto]),
                        "sku": str(row[col_codigo])
                    })
                
                if len(lista_produtos) > 0:
                    st.divider()
                    st.info("📸 **A câmera está liberada!** Tire a foto do produto para receber a porcentagem de precisão.")
                    
                    foto_tirada = st.camera_input("Fotografe a peça:")
                    
                    if foto_tirada:
                        img_original = Image.open(foto_tirada).convert('RGB')
                        
                        with st.spinner("📊 Analisando imagem e calculando compatibilidade..."):
                            try:
                                client = genai.Client(api_key=CHAVE_GOOGLE_FIXA)
                                
                                buffered = BytesIO()
                                img_original.save(buffered, format="JPEG")
                                image_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                                
                                prompt = f"""
                                Você é o especialista sênior de estoque da loja Mocinha Biju.
                                Analise a foto enviada e compare com a lista de produtos abaixo.
                                
                                Lista JSON dos produtos cadastrados:
                                {json.dumps(lista_produtos, ensure_ascii=False)}
                                
                                TAREFA:
                                1. Encontre as 3 melhores opções de produtos correspondentes na lista.
                                2. Atribua uma porcentagem estimada de precisão/compatibilidade (ex: 95, 80, 60) baseada nos detalhes visuais.
                                3. Retorne EXATAMENTE UM ARRAY JSON contendo 3 dicionários com as chaves 'id' e 'precisao'.
                                Exemplo exato do formato esperado:
                                [
                                    {{"id": "0", "precisao": "98%"}},
                                    {{"id": "1", "precisao": "82%"}},
                                    {{"id": "2", "precisao": "65%"}}
                                ]
                                Retorne APENAS o JSON puro, sem crases, sem formatação markdown e sem texto adicional.
                                """
                                
                                interaction = client.interactions.create(
                                    model="gemini-3.6-flash",
                                    input=[
                                        {
                                            "type": "image",
                                            "mime_type": "image/jpeg",
                                            "data": image_b64,
                                        },
                                        {"type": "text", "text": prompt},
                                    ],
                                )
                                
                                texto_puro = interaction.output_text.replace('```json', '').replace('```', '').strip()
                                itens_recomendados = json.loads(texto_puro)
                                
                                st.subheader("🎯 Resultados com Taxa de Precisão:")
                                
                                for rank, item_rec in enumerate(itens_recomendados):
                                    id_rec = item_rec.get("id")
                                    precisao = item_rec.get("precisao", "N/A")
                                    
                                    produto = next((item for item in lista_produtos if item["id"] == id_rec), None)
                                    if produto:
                                        st.markdown(f"### {rank+1}º Lugar: {produto['nome']} — **Compatibilidade: {precisao}**")
                                        st.write(f"**Código de Barras:** `{produto['sku']}`")
                                        st.divider()
                                            
                            except Exception as e:
                                st.error(f"Erro na análise de precisão: {e}")
    else:
        st.error("Não foi possível carregar os dados da planilha do OneDrive. Verifique o link.")
else:
    st.warning("👈 Conecte o Bling na barra lateral para iniciar o sistema.")
