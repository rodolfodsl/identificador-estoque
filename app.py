import streamlit as st
import pandas as pd
import requests
import base64
from io import BytesIO
from PIL import Image
import json

st.set_page_config(page_title="Identificador Gemini", layout="centered")
st.title("🧠 Identificador Visual com Gemini")

# --- CREDENCIAIS FIXAS DO BLING ---
CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534".strip()
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25".strip()

st.sidebar.header("🔑 Conectar Sistemas")
gemini_key = st.sidebar.text_input("Sua Chave API do Gemini:", type="password")
auth_code_input = st.sidebar.text_input("Código de Autorização do Bling:")

if st.sidebar.button("🔗 Conectar Tudo"):
    if gemini_key and auth_code_input:
        with st.spinner("Conectando..."):
            token_url = "https://api.bling.com.br/Api/v3/oauth/token"
            credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers = {"Authorization": f"Basic {encoded_credentials}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "1.0"}
            data = {"grant_type": "authorization_code", "code": auth_code_input.strip()}
            
            try:
                resp_token = requests.post(token_url, headers=headers, data=data)
                token_data = resp_token.json()
                if "access_token" in token_data:
                    st.session_state['bling_token'] = token_data["access_token"]
                    st.session_state['gemini_key'] = gemini_key.strip()
                    st.success("Sistemas Conectados!")
                    st.rerun()
                else:
                    st.sidebar.error("Código do Bling expirado. Gere outro no painel.")
            except Exception as e:
                st.sidebar.error(f"Erro: {e}")
    else:
        st.sidebar.warning("Preencha as duas chaves.")

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

if 'bling_token' in st.session_state and 'gemini_key' in st.session_state:
    st.success("✅ Bling e Gemini Conectados!")
    st.divider()
    
    arquivo_csv = st.file_uploader("Arraste o arquivo .csv do Bling", type=['csv'])
    
    if arquivo_csv:
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        if 'ID' in df.columns and 'Descrição' in df.columns:
            termo = st.text_input("Qual categoria vamos buscar? (Ex: RELÓGIO):")
            
            if termo:
                df_filtrado = df[df['Descrição'].str.contains(termo.upper(), na=False)].copy()
                st.write(f"Encontrados **{len(df_filtrado)}** itens no catálogo.")
                
                lista_produtos = []
                for _, row in df_filtrado.iterrows():
                    lista_produtos.append({"id": str(row['ID']), "nome": str(row['Descrição']), "sku": str(row.get('Código', ''))})
                
                if len(lista_produtos) > 0:
                    st.divider()
                    st.info("📸 **A câmera está liberada!** Tire a foto do produto e aguarde a mágica.")
                    
                    foto_tirada = st.camera_input("Fotografe a peça:")
                    
                    if foto_tirada:
                        img_original = Image.open(foto_tirada).convert('RGB')
                        
                        with st.spinner("🤖 Olhando para a sua foto e lendo o estoque da Mocinha Biju..."):
                            try:
                                # BYPASS: Conexão Direta com o Servidor (Ignora a biblioteca com defeito)
                                buffered = BytesIO()
                                img_original.save(buffered, format="JPEG")
                                img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                                
                                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.session_state['gemini_key']}"
                                
                                prompt = f"""
                                Você é o especialista de estoque visual da loja Mocinha Biju.
                                Analise a foto que estou enviando deste produto real.
                                
                                Aqui está a lista JSON dos produtos dessa categoria:
                                {json.dumps(lista_produtos, ensure_ascii=False)}
                                
                                TAREFA:
                                1. Observe os detalhes visuais da foto (formato do visor, cor do mostrador, cor da pulseira, tipo de metal/material, etc).
                                2. Leia os 'nome' na lista e encontre as 3 opções que descrevem mais perfeitamente a imagem.
                                3. Retorne EXATAMENTE UM ARRAY JSON com os 3 'id' correspondentes em ordem de probabilidade.
                                Exemplo de retorno: ["16629916212", "16629916213", "16629916214"]
                                NÃO adicione crases (```), formatação markdown, nem palavras. Apenas o array JSON puro.
                                """
                                
                                payload = {
                                    "contents": [{
                                        "parts": [
                                            {"text": prompt},
                                            {"inline_data": {"mime_type": "image/jpeg", "data": img_base64}}
                                        ]
                                    }]
                                }
                                
                                resp_gemini = requests.post(gemini_url, headers={"Content-Type": "application/json"}, json=payload)
                                dados_gemini = resp_gemini.json()
                                
                                if "error" in dados_gemini:
                                    st.error(f"Erro do Google: {dados_gemini['error']['message']}")
                                else:
                                    texto_resposta = dados_gemini['candidates'][0]['content']['parts'][0]['text']
                                    texto_puro = texto_resposta.replace('```json', '').replace('```', '').strip()
                                    ids_recomendados = json.loads(texto_puro)
                                    
                                    st.subheader("🎯 Resultado do Gemini:")
                                    
                                    for rank, id_rec in enumerate(ids_recomendados):
                                        produto = next((item for item in lista_produtos if item["id"] == id_rec), None)
                                        if produto:
                                            st.markdown(f"### {rank+1}º Lugar: {produto['nome']}")
                                            col_1, col_2 = st.columns([1, 2])
                                            with col_1:
                                                img_oficial = baixar_foto_bling_unica(produto['id'], st.session_state['bling_token'])
                                                if img_oficial:
                                                    st.image(img_oficial, width=150)
                                                else:
                                                    st.warning("Sem foto no Bling")
                                            with col_2:
                                                st.write(f"**SKU:** `{produto['sku']}`")
                                            st.divider()
                                            
                            except Exception as e:
                                st.error(f"Erro no processamento da imagem: {e}")
