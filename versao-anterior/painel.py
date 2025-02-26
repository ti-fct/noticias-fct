from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.carousel import Carousel
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.config import Config
from kivy.uix.image import AsyncImage
from kivy.animation import Animation
from kivy.core.window import Window

import feedparser
from bs4 import BeautifulSoup
import logging
import locale
from datetime import datetime
from urllib.parse import urljoin
import qrcode
import os
from email.utils import parsedate_to_datetime

# Configuração inicial para tela cheia
Config.set('graphics', 'fullscreen', 'auto')
Config.set('graphics', 'borderless', '1')  # Remove a borda da janela
Config.write()  # Salva as configurações

# Configurações gerais
logging.basicConfig(level=logging.INFO)
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error as e:
    logging.warning("Locale pt_BR.UTF-8 não está disponível, usando configuração padrão.")

class RootWidget(BoxLayout):
    pass

class NewsItem(BoxLayout):
    title = StringProperty('')
    content = StringProperty('')
    image_source = StringProperty('')
    pub_date = StringProperty('')
    qr_code = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._finalizar_inicializacao)

    def _finalizar_inicializacao(self, dt):
        if not self.image_source:
            self.image_source = 'assets/placeholder.png'

class NewsCarousel(Carousel):
    news_items = ListProperty([])
    BASE_URL = 'https://fct.ufg.br'
    auto_advance = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.direction = 'right'
        self.loop = True
        self.anim_type = 'in_out_expo'
        self.anim_move_duration = 0.7
        self.min_move = 0.05
        self.qr_dir = 'qrcodes'
        
        os.makedirs(self.qr_dir, exist_ok=True)
        
        # Inicializa o carregamento de notícias
        Clock.schedule_once(self.carregar_noticias)
        Clock.schedule_interval(self.carregar_noticias, 300)
        
        # Agenda o primeiro slide automático com um pequeno atraso
        Clock.schedule_once(lambda dt: self.iniciar_slides_automaticos(), 2)
        
        # Vincula eventos de tela cheia
        Window.bind(on_resize=self._on_window_resize)
        Window.bind(on_maximize=self._on_window_maximize)

    def _on_window_resize(self, instance, width, height):
        """Manipula eventos de redimensionamento da janela"""
        Clock.unschedule(self.passar_slide_automatico)
        Clock.schedule_once(lambda dt: self.iniciar_slides_automaticos(), 1)

    def _on_window_maximize(self, instance):
        """Manipula eventos de maximização da janela"""
        Clock.unschedule(self.passar_slide_automatico)
        Clock.schedule_once(lambda dt: self.iniciar_slides_automaticos(), 1)

    def iniciar_slides_automaticos(self):
        """Inicia ou reinicia a apresentação automática de slides"""
        if self.auto_advance:
            Clock.unschedule(self.passar_slide_automatico)
            Clock.schedule_interval(self.passar_slide_automatico, 10)
            logging.info("Apresentação automática de slides iniciada/reiniciada")

    def pausar_slides_automaticos(self):
        """Pausa a apresentação automática de slides"""
        Clock.unschedule(self.passar_slide_automatico)
        logging.info("Apresentação automática de slides pausada")

    def passar_slide_automatico(self, dt):
        """Passa os slides automaticamente"""
        if not self.slides or not self.auto_advance:
            return False

        try:
            # Garante que o índice seja válido
            total_slides = len(self.slides)
            if total_slides <= 1:
                return False

            # Avança para o próximo slide
            próximo_índice = (self.index + 1) % total_slides
            self.index = próximo_índice
            
            logging.info(f"Avançando para slide {próximo_índice + 1} de {total_slides}")
            return True
            
        except Exception as e:
            logging.error(f"Erro ao passar slide: {e}")
            return False

    def gerar_qr_code(self, url, news_id):
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            caminho_qr = os.path.join(self.qr_dir, f'qr_{news_id}.png')
            qr_img.save(caminho_qr)
            return caminho_qr
        except Exception as e:
            logging.error(f"Erro no QR code: {e}")
            return ''

    def formatar_data(self, data_str):
        try:
            data = parsedate_to_datetime(data_str)
            return data.strftime('%d/%m/%Y')
        except Exception as e:
            logging.error(f"Erro na formatação da data: {e}")
            return data_str

    def corrigir_url_imagem(self, url):
        if not url:
            return 'assets/placeholder.png'
        if url.startswith("http://fct.ufg.brhttps://"):
            url = url.replace("http://fct.ufg.br", "")
        if not url.startswith(('http://', 'https://')):
            return urljoin(self.BASE_URL, url)
        return url

    def extrair_conteudo_principal(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        img_tag = soup.find('img')
        img_url = self.corrigir_url_imagem(img_tag['src']) if img_tag else None
        
        texto_principal = [
            p.get_text().strip() for p in soup.find_all('p') 
            if p.get_text().strip() and not any(m in p.get_text().lower() for m in ['texto:', 'foto:'])
        ]
        
        conteudo = ' '.join(texto_principal[:5])
        if len(conteudo) > 1000:
            conteudo = conteudo[:1000] + '...'
        return conteudo, img_url

    def carregar_noticias(self, *args):
        try:
            feed = feedparser.parse('https://fct.ufg.br/feed')
            noticias_processadas = []
            
            for idx, entrada in enumerate(feed.entries[:5]):
                conteudo, img_url = self.extrair_conteudo_principal(entrada.get('description', ''))
                titulo = entrada.title if len(entrada.title) <= 80 else entrada.title[:80] + '...'
                pub_date = self.formatar_data(entrada.published) if 'published' in entrada else ''
                noticias_processadas.append({
                    'title': titulo,
                    'content': conteudo,
                    'image_source': img_url or 'assets/placeholder.png',
                    'pub_date': pub_date,
                    'qr_code': self.gerar_qr_code(entrada.link, idx)
                })
            
            self.news_items = noticias_processadas
            self._criar_slides()
            
        except Exception as e:
            logging.error(f"Erro ao carregar notícias: {e}")

    def _criar_slides(self):
        self.clear_widgets()
        for item in self.news_items:
            self.add_widget(NewsItem(**item))

class NewsPanel(App):
    clock_text = StringProperty('')
    
    def build(self):
        self.title = 'Painel FCT/UFG'
        Clock.schedule_interval(self.atualizar_relogio, 1)
        
        # Configura a janela para tela cheia
        Window.borderless = True
        Window.fullscreen = True
        
        return Builder.load_file('painel.kv')
    
    def atualizar_relogio(self, dt):
        self.clock_text = datetime.now().strftime("%H:%M:%S")

if __name__ == '__main__':
    NewsPanel().run()