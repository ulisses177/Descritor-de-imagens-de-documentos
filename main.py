import os
import fitz
import base64
import json
import logging
from dataclasses import dataclass
from typing import List, Dict
from dotenv import load_dotenv
from openai import AzureOpenAI

# Configuração básica
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

# Configurar cliente Azure OpenAI
client = AzureOpenAI(
    azure_endpoint=os.getenv("AOAI_ENDPOINT"),
    api_key=os.getenv("AOAI_API_KEY"),
    api_version="2024-02-15-preview"
)
deployment_name = os.getenv("AOAI_DEPLOYMENT")

# Prompt template para descrição de imagens
image_description_prompt = """
Descreva esta imagem de forma objetiva e detalhada, considerando que ela faz parte de um tutorial de sistema.
Considere o contexto do documento ao fazer a descrição.
"""

@dataclass
class ImageDescription:
    image_name: str
    path: str
    description: str

@dataclass
class DocumentResult:
    document_id: str
    descriptions: List[ImageDescription]

class DocumentProcessor:
    def __init__(self):
        self.base_dir = "output"
        self.docs_dir = "docs"
        os.makedirs(self.base_dir, exist_ok=True)
    
    def process_images(self, pdf_path: str) -> List[ImageDescription]:
        """
        Extrai e processa imagens do PDF, gerando descrições
        """
        doc = fitz.open(pdf_path)
        doc_name = os.path.splitext(os.path.basename(pdf_path))[0]
        image_descriptions = []
        
        # Criar diretório para as imagens
        image_dir = os.path.join(self.base_dir, doc_name, "images")
        os.makedirs(image_dir, exist_ok=True)
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            images = page.get_images(full=True)
            
            for img_index, img in enumerate(images):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    
                    if not base_image:
                        continue
                    
                    # Salvar imagem
                    image_name = f"image_{page_num + 1}_{img_index + 1}.{base_image['ext']}"
                    image_path = os.path.join(image_dir, image_name)
                    
                    with open(image_path, "wb") as img_file:
                        img_file.write(base_image["image"])
                    
                    # Gerar descrição
                    description = self.get_image_description(image_path)
                    
                    # Criar objeto ImageDescription
                    image_desc = ImageDescription(
                        image_name=image_name,
                        path=image_path,
                        description=description
                    )
                    
                    image_descriptions.append(image_desc)
                    
                    logging.info(f"Processada imagem {image_name}")
                    
                except Exception as e:
                    logging.error(f"Erro ao processar imagem: {e}")
                    continue
        
        doc.close()
        return image_descriptions
    
    def get_image_description(self, image_path: str) -> str:
        """
        Gera descrição da imagem usando Azure OpenAI
        """
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            response = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": "Você é um assistente especializado em descrever imagens."},
                    {"role": "user", "content": image_description_prompt + f"\n![Imagem]({image_path})"}
                ]
            )
            return response.choices[0].message.content
            
        except Exception as e:
            logging.error(f"Erro ao gerar descrição: {e}")
            return "Erro na geração da descrição"
    
    def save_results(self, doc_result: DocumentResult):
        """
        Salva resultados em JSON e gera relatório HTML
        """
        doc_dir = os.path.join(self.base_dir, doc_result.document_id)
        os.makedirs(doc_dir, exist_ok=True)
        
        # Salvar JSON
        result_dict = {
            "document_id": doc_result.document_id,
            "descriptions": [
                {
                    "image_name": desc.image_name,
                    "path": os.path.relpath(desc.path, doc_dir),
                    "description": desc.description
                }
                for desc in doc_result.descriptions
            ]
        }
        
        json_path = os.path.join(doc_dir, "results.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2)
        
        # Gerar relatório HTML
        generate_html_report(doc_result)

def generate_html_report(doc_result: DocumentResult):
    """
    Gera um relatório HTML com imagens e suas descrições
    """
    doc_dir = os.path.join("output", doc_result.document_id)
    html_path = os.path.join(doc_dir, "report.html")
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Relatório de Imagens - {doc_id}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .header {{
                background-color: #333;
                color: white;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 5px;
            }}
            .image-container {{
                background-color: white;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 5px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .image-row {{
                display: flex;
                margin-bottom: 20px;
            }}
            .image-col {{
                flex: 1;
                padding: 10px;
            }}
            .description-col {{
                flex: 2;
                padding: 10px;
            }}
            img {{
                max-width: 100%;
                height: auto;
                border: 1px solid #ddd;
                border-radius: 4px;
            }}
            .description {{
                background-color: #f9f9f9;
                padding: 15px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Relatório de Imagens - {doc_id}</h1>
        </div>
        
        <div class="image-container">
            {images_html}
        </div>
    </body>
    </html>
    """
    
    # Gerar HTML para imagens e descrições
    images_html = ""
    for desc in doc_result.descriptions:
        image_path = os.path.relpath(desc.path, doc_dir)
        images_html += f"""
        <div class="image-row">
            <div class="image-col">
                <img src="{image_path}" alt="{desc.image_name}">
                <p><strong>{desc.image_name}</strong></p>
            </div>
            <div class="description-col">
                <div class="description">
                    <p>{desc.description}</p>
                </div>
            </div>
        </div>
        """
    
    # Gerar HTML final
    html_content = html_template.format(
        doc_id=doc_result.document_id,
        images_html=images_html
    )
    
    # Salvar arquivo HTML
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    logging.info(f"Relatório HTML gerado: {html_path}")

def main():
    processor = DocumentProcessor()
    
    # Processar todos os PDFs na pasta docs
    for pdf_file in os.listdir(processor.docs_dir):
        if not pdf_file.endswith('.pdf'):
            continue
        
        pdf_path = os.path.join(processor.docs_dir, pdf_file)
        doc_name = os.path.splitext(pdf_file)[0]
        
        logging.info(f"Processando documento: {pdf_file}")
        
        # Processar imagens e gerar descrições
        descriptions = processor.process_images(pdf_path)
        
        # Se não houver imagens, pular para o próximo documento
        if not descriptions:
            logging.info(f"Nenhuma imagem encontrada em: {pdf_file}")
            continue
        
        # Criar resultado do documento
        doc_result = DocumentResult(
            document_id=doc_name,
            descriptions=descriptions
        )
        
        # Salvar resultados
        processor.save_results(doc_result)
        
        logging.info(f"Processamento concluído para: {doc_name}")
    
    logging.info("\nProcessamento concluído!")

if __name__ == "__main__":
    main()
