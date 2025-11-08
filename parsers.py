# parsers.py
from bs4 import BeautifulSoup
import re
import requests
from models import db, Dance, DanceType, DanceFormat, SetType


class DancePageParser:
    """Парсер страницы с информацией о танце"""
    
    def __init__(self, html_content):
        self.soup = BeautifulSoup(html_content, 'html.parser')
    
    def parse_dance_data(self):
        """Основной метод парсинга данных о танце"""
        # Сначала парсим основную информационную строку
        main_info = self._parse_main_info_string()
        
        return {
            'name': self._parse_name(),
            'dance_type': self._parse_dance_type(),
            'meter': self._parse_meter(),
            'bars': self._parse_bars(),  # код тактов (J48, R32)
            'bars_count': self._parse_bars_count(),  # числовое значение тактов для size_id
            'formation': main_info.get('formation', self._parse_formation()),
            'couples_count': main_info.get('couples_count', self._parse_couples_count()),
            'set_format': main_info.get('set_format', self._parse_couples_count()),  # Используем set_format из main_info
            'progression': self._parse_progression(),
            'repetitions': self._parse_repetitions(),  # числовое значение повторений для count_id
            'author': self._parse_author(),
            'year': self._parse_year(),
            'description': self._parse_description(),
            'steps': self._parse_steps(),
            'published_in': self._parse_publications(),
            'recommended_music': self._parse_music(),
            'figures': self._parse_figures(),
            'extra_info': self._parse_extra_info(),
            'intensity': self._parse_intensity(),
            'formations_list': self._parse_formations_list(),
            'images': self._parse_images(),
            'source_url': self._parse_source_url()
        }
    
    def _parse_main_info_string(self):
        """Парсинг основной информационной строки типа 'Jig · 32 bars · 3 couples · Longwise - 4'"""
        result = {
            'couples_count': None,
            'set_format': None,
            'formation': None
        }
        
        first_p = self.soup.find('h1')
        if first_p:
            first_p = first_p.find_next('p')
            if first_p:
                text = first_p.get_text().strip()
                print(f"🔍 Основная строка: '{text}'")
                
                # Ищем количество пар (3 couples)
                couples_match = re.search(r'(\d+)\s+couples?', text, re.IGNORECASE)
                if couples_match:
                    result['couples_count'] = int(couples_match.group(1))
                    print(f"✅ Найдено couples_count: {result['couples_count']}")
                
                # Ищем формацию и формат сета (Longwise - 4)
                # Варианты: "Longwise - 4", "Longwise-4", "Square set - 8" и т.д.
                formation_patterns = [
                    r'(Longwise|Square|Triangular|Circular)\s*-\s*(\d+)',
                    r'(Longwise|Square|Triangular|Circular)\s+set\s*-\s*(\d+)'
                ]
                
                for pattern in formation_patterns:
                    formation_match = re.search(pattern, text, re.IGNORECASE)
                    if formation_match:
                        formation_name = formation_match.group(1)
                        set_format = int(formation_match.group(2))
                        
                        # Определяем полное название формации
                        formation_mapping = {
                            'Longwise': 'Longwise set',
                            'Square': 'Square set', 
                            'Triangular': 'Triangular set',
                            'Circular': 'Circular set'
                        }
                        
                        result['formation'] = formation_mapping.get(formation_name, 'Longwise set')
                        result['set_format'] = set_format
                        print(f"✅ Найдено formation: {result['formation']}, set_format: {result['set_format']}")
                        break
                
                # Если не нашли через тире, ищем просто формацию
                if not result['formation']:
                    formation_mapping = {
                        'Longwise': 'Longwise set',
                        'Square': 'Square set', 
                        'Triangular': 'Triangular set',
                        'Circular': 'Circular set'
                    }
                    
                    for key in formation_mapping:
                        if key.lower() in text.lower():
                            result['formation'] = formation_mapping[key]
                            print(f"✅ Найдено formation (без формата): {result['formation']}")
                            break
                
                # Если нашли формацию, но не нашли set_format, используем couples_count как fallback
                if result['formation'] and not result['set_format'] and result['couples_count']:
                    result['set_format'] = result['couples_count']
                    print(f"⚠️  set_format не найден, используем couples_count: {result['set_format']}")
        
        return result
    
    def _parse_name(self):
        """Парсинг названия танца"""
        title_element = self.soup.find('span', {'id': 'title'})
        return title_element.get_text().strip() if title_element else 'Неизвестный танец'
    
    def _parse_dance_type(self):
        """Парсинг типа танца (Jig, Reel, etc)"""
        dance_types = {
            'Jig': 'Jig',
            'Reel': 'Reel', 
            'Strathspey': 'Strathspey',
            'March': 'March',
            'Waltz': 'Waltz',
            'Polka': 'Polka'
        }
        
        first_p = self.soup.find('h1')
        if first_p:
            first_p = first_p.find_next('p')
            if first_p:
                text = first_p.get_text()
                for key, value in dance_types.items():
                    if key in text:
                        return value
        return 'Unknown'
    
    def _parse_meter(self):
        """Парсинг размера (4/4L, 3/4, etc)"""
        first_p = self.soup.find('h1')
        if first_p:
            first_p = first_p.find_next('p')
            if first_p:
                text = first_p.get_text()
                meter_match = re.search(r'(\d+/\d+[A-Z]*)', text)
                return meter_match.group(1) if meter_match else None
        return None
    
    def _parse_bars(self):
        """Парсинг кода тактов (J48, R32, etc) - для заметки"""
        first_p = self.soup.find('h1')
        if first_p:
            first_p = first_p.find_next('p')
            if first_p:
                text = first_p.get_text()
                bars_match = re.search(r'([A-Z]\d+)', text)
                return bars_match.group(1) if bars_match else None
        return None
    
    def _parse_bars_count(self):
        """Парсинг количества тактов (числовое значение для size_id)"""
        first_p = self.soup.find('h1')
        if first_p:
            first_p = first_p.find_next('p')
            if first_p:
                text = first_p.get_text()
                bars_match = re.search(r'(\d+)\s*bars', text, re.IGNORECASE)
                if bars_match:
                    return int(bars_match.group(1))
        
        bars_code = self._parse_bars()
        if bars_code:
            num_match = re.search(r'(\d+)', bars_code)
            if num_match:
                return int(num_match.group(1))
        
        return 32  # значение по умолчанию
    
    def _parse_formation(self):
        """Парсинг формации (типа сета) - Longwise, Square, Triangular, Circular"""
        formation_mapping = {
            'Longwise': 'Longwise set',
            'Square': 'Square set', 
            'Triangular': 'Triangular set',
            'Circular': 'Circular set'
        }
        
        # Дополнительный поиск в структурированных данных
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Formation' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    formation_text = dd.get_text().strip()
                    for key in formation_mapping:
                        if key in formation_text:
                            return formation_mapping[key]
        
        return 'Longwise set'  # значение по умолчанию
    
    def _parse_couples_count(self):
        """Парсинг количества пар (из основной информации) - это минимальное количество пар"""
        # Дополнительный поиск в структурированных данных
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Couples' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    couples_text = dd.get_text().strip()
                    couples_match = re.search(r'(\d+)', couples_text)
                    if couples_match:
                        return int(couples_match.group(1))
        
        return 4  # значение по умолчанию
    
    def _parse_progression(self):
        """Парсинг прогрессии"""
        first_p = self.soup.find('h1')
        if first_p:
            first_p = first_p.find_next('p')
            if first_p:
                text = first_p.get_text()
                prog_match = re.search(r'Progression:\s*(\d+)', text)
                return prog_match.group(1) if prog_match else None
        return None
    
    def _parse_repetitions(self):
        """Парсинг количества повторений"""
        first_p = self.soup.find('h1')
        if first_p:
            first_p = first_p.find_next('p')
            if first_p:
                text = first_p.get_text()
                rep_match = re.search(r'repetitions:\s*(\d+)', text, re.IGNORECASE)
                if rep_match:
                    return int(rep_match.group(1))
        
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'repetitions' in dt.get_text().lower():
                dd = dt.find_next_sibling('dd')
                if dd:
                    text = dd.get_text()
                    rep_match = re.search(r'(\d+)', text)
                    if rep_match:
                        return int(rep_match.group(1))
        
        return 4  # значение по умолчанию
    
    def _parse_author(self):
        """Парсинг автора"""
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Devised by' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    author_link = dd.find('a')
                    return author_link.get_text().strip() if author_link else dd.get_text().strip()
        return 'Unknown'
    
    def _parse_year(self):
        """Парсинг года создания"""
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Devised by' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    text = dd.get_text()
                    year_match = re.search(r'\((\d{4})\)', text)
                    return int(year_match.group(1)) if year_match else None
        return None
    
    def _parse_description(self):
        """Парсинг описания - предпочтительно из MiniCribs, затем E-cribs"""
        cribs_tab = self.soup.find('div', {'id': 'cribs'})
        if cribs_tab:
            mini_cribs = cribs_tab.find('div', class_='minicribs')
            if mini_cribs:
                description_text = mini_cribs.get_text().strip()
                if description_text:
                    print("✅ Найдено описание в MiniCribs")
                    return description_text
            
            e_cribs = cribs_tab.find('div', class_='cribtext')
            if e_cribs:
                description_text = e_cribs.get_text().strip()
                if description_text:
                    print("✅ Найдено описание в E-cribs")
                    return description_text
        
        crib_div = self.soup.find('div', class_='cribtext')
        if crib_div:
            description_text = crib_div.get_text().strip()
            if description_text:
                print("✅ Найдено описание в основном блоке")
                return description_text
        
        print("❌ Описание не найдено")
        return None
    
    def _parse_steps(self):
        """Парсинг шагов"""
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Steps' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    steps_text = dd.get_text().strip()
                    return [step.strip() for step in steps_text.split(',')]
        return []
    
    def _parse_publications(self):
        """Парсинг публикаций"""
        publications = []
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Published in' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    pub_links = dd.find_all('a')
                    for link in pub_links:
                        publications.append(link.get_text().strip())
        return publications
    
    def _parse_music(self):
        """Парсинг рекомендованной музыки"""
        music = []
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Recommended Music' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    music_links = dd.find_all('a')
                    for link in music_links:
                        music.append(link.get_text().strip())
        return music
    
    def _parse_figures(self):
        """Парсинг фигур по тактам"""
        figures = []
        crib_div = self.soup.find('div', class_='cribtext')
        if crib_div:
            dance_dl = crib_div.find('dl', class_='dance')
            if dance_dl:
                current_bars = None
                for element in dance_dl.children:
                    if element.name == 'dt':
                        current_bars = element.get_text().strip()
                    elif element.name == 'dd' and current_bars:
                        description = element.get_text().strip()
                        figures.append({
                            'bars': current_bars,
                            'description': description
                        })
                        current_bars = None
        return figures
    
    def _parse_extra_info(self):
        """Парсинг дополнительной информации из вкладки Extra Info"""
        extra_tab = self.soup.find('div', {'id': 'extrainfo'})
        if extra_tab:
            elements = extra_tab.find_all(['p', 'div', 'span'])
            extra_info = ""
            
            for element in elements:
                text = element.get_text().strip()
                if text and len(text) > 5 and text not in extra_info:
                    extra_info += text + "\n\n"
            
            if extra_info.strip():
                return extra_info.strip()
            
            text_content = extra_tab.get_text().strip()
            if text_content and len(text_content) > 10:
                return text_content
        
        extra_dl = self.soup.find('dl', class_='row')
        if extra_dl:
            dt_elements = extra_dl.find_all('dt', class_='col-sm-2 text-sm-end')
            for dt in dt_elements:
                if 'Extra Info' in dt.get_text():
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        return dd.get_text().strip()
        
        return ""
    
    def _parse_intensity(self):
        """Парсинг интенсивности танца"""
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Intensity' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    intensity_text = dd.get_text().strip()
                    intensity_match = re.search(r'(\d+%)', intensity_text)
                    if intensity_match:
                        return intensity_match.group(1)
                    return intensity_text
        return None
    
    def _parse_formations_list(self):
        """Парсинг списка формаций"""
        formations = []
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Formations' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    formation_links = dd.find_all('a')
                    for link in formation_links:
                        formation_name = link.get_text().strip()
                        if formation_name and formation_name not in formations:
                            formations.append(formation_name)
        return formations
    
    def _parse_source_url(self):
        """Парсинг исходного URL"""
        canonical_link = self.soup.find('link', {'rel': 'canonical'})
        if canonical_link and canonical_link.get('href'):
            return canonical_link.get('href')
        
        og_url = self.soup.find('meta', {'property': 'og:url'})
        if og_url and og_url.get('content'):
            return og_url.get('content')
        
        return None

    def _parse_images(self):
        """Парсинг изображений из вкладки Cribs"""
        images = []
        
        cribs_tab = self.soup.find('div', {'id': 'cribs'})
        if not cribs_tab:
            print("❌ Вкладка Cribs не найдена")
            return images
        
        print("✅ Найдена вкладка Cribs")
        
        img_elements = cribs_tab.find_all('img')
        print(f"🔍 Найдено тегов img: {len(img_elements)}")
        
        for img in img_elements:
            src = img.get('src')
            if src:
                full_url = self._make_absolute_url(src)
                alt = img.get('alt', 'Diagram')
                image_type = self._determine_image_type(full_url, alt)
                
                images.append({
                    'url': full_url,
                    'alt': alt,
                    'filename': self._extract_filename(src),
                    'type': image_type
                })
                print(f"🖼️  Найдено изображение ({image_type}): {full_url}")
        
        svg_objects = cribs_tab.find_all('object', {'type': 'image/svg+xml'})
        for svg_obj in svg_objects:
            data = svg_obj.get('data')
            if data:
                full_url = self._make_absolute_url(data)
                images.append({
                    'url': full_url,
                    'alt': 'SVG Diagram',
                    'filename': self._extract_filename(data),
                    'type': 'diagram'
                })
                print(f"🖼️  Найден SVG: {full_url}")
        
        image_links = cribs_tab.find_all('a', href=re.compile(r'\.(png|jpg|jpeg|gif|svg|webp)', re.I))
        for link in image_links:
            href = link.get('href')
            if href and href not in [img['url'] for img in images]:
                full_url = self._make_absolute_url(href)
                alt = link.get_text().strip() or 'Linked Diagram'
                image_type = self._determine_image_type(full_url, alt)
                
                images.append({
                    'url': full_url,
                    'alt': alt,
                    'filename': self._extract_filename(href),
                    'type': image_type
                })
                print(f"🖼️  Найдена ссылка на изображение ({image_type}): {full_url}")
        
        print(f"📊 Итого изображений: {len(images)}")
        return images

    def _determine_image_type(self, url, alt_text):
        """Определение типа изображения на основе URL и alt текста"""
        alt_lower = alt_text.lower()
        url_lower = url.lower()
        
        type_keywords = {
            'diagram': ['diagram', 'diag', 'схема', 'диаграмма'],
            'music': ['music', 'sheet', 'ноты', 'партитура'],
            'author': ['author', 'composer', 'автор', 'композитор'],
            'formation': ['formation', 'формация', 'построение']
        }
        
        for image_type, keywords in type_keywords.items():
            if any(word in alt_lower for word in keywords):
                return image_type
        
        for image_type, keywords in type_keywords.items():
            if any(word in url_lower for word in keywords):
                return image_type
        
        return 'diagram'  # по умолчанию считаем диаграммой

    def _make_absolute_url(self, relative_url):
        """Преобразование относительного URL в абсолютный"""
        if relative_url.startswith('http'):
            return relative_url
        elif relative_url.startswith('//'):
            return 'https:' + relative_url
        elif relative_url.startswith('/'):
            return 'https://my.strathspey.org' + relative_url
        else:
            return 'https://my.strathspey.org/' + relative_url

    def _extract_filename(self, url):
        """Извлечение имени файла из URL"""
        if not url:
            return 'diagram.svg'
        
        url = url.split('?')[0]
        filename = url.split('/')[-1]
        
        if not filename or '.' not in filename:
            if 'svg' in url.lower():
                return 'diagram.svg'
            else:
                return 'diagram.png'
        
        return filename


class BatchDanceParser:
    """Класс для пакетной обработки нескольких танцев"""
    
    def __init__(self):
        self.parsed_dances = []
        self.errors = []
    
    def parse_multiple_dances(self, html_contents):
        """Парсинг нескольких HTML страниц"""
        for i, html_content in enumerate(html_contents):
            try:
                parser = DancePageParser(html_content)
                dance_data = parser.parse_dance_data()
                self.parsed_dances.append(dance_data)
            except Exception as e:
                self.errors.append(f"Ошибка при парсинге танца {i+1}: {str(e)}")
        
        return {
            'successful': self.parsed_dances,
            'errors': self.errors,
            'total_parsed': len(self.parsed_dances),
            'total_errors': len(self.errors)
        }


def extract_dance_id_from_url(url):
    """Извлечение ID танца из URL"""
    if not url:
        return None
    match = re.search(r'/dance/(\d+)/', url)
    return match.group(1) if match else None


def validate_dance_data(dance_data):
    """Валидация данных танца"""
    errors = []
    
    if not dance_data.get('name') or dance_data['name'] == 'Неизвестный танец':
        errors.append("Отсутствует название танца")
    
    if not dance_data.get('author') or dance_data['author'] == 'Unknown':
        errors.append("Отсутствует автор танца")
    
    if not dance_data.get('description'):
        errors.append("Отсутствует описание танца")
    
    return errors

################
### ОТЛАДКА
def parse_dance_data(self):
    """Основной метод парсинга данных о танце"""
    # Сначала парсим основную информационную строку
    main_info = self._parse_main_info_string()
    
    data = {
        'name': self._parse_name(),
        'dance_type': self._parse_dance_type(),
        'meter': self._parse_meter(),
        'bars': self._parse_bars(),
        'bars_count': self._parse_bars_count(),
        'formation': main_info.get('formation', self._parse_formation()),
        'couples_count': main_info.get('couples_count', self._parse_couples_count()),
        'set_format': main_info.get('set_format', self._parse_couples_count()),
        'progression': self._parse_progression(),
        'repetitions': self._parse_repetitions(),
        'author': self._parse_author(),
        'year': self._parse_year(),
        'description': self._parse_description(),
        'steps': self._parse_steps(),
        'published_in': self._parse_publications(),
        'recommended_music': self._parse_music(),
        'figures': self._parse_figures(),
        'extra_info': self._parse_extra_info(),
        'intensity': self._parse_intensity(),
        'formations_list': self._parse_formations_list(),
        'images': self._parse_images(),
        'source_url': self._parse_source_url()
    }
    
    # ДОБАВИТЬ ЭТОТ ОТЛАДОЧНЫЙ ВЫВОД:
    print("🎯 РЕЗУЛЬТАТ ПАРСИНГА:")
    print(f"   Название: {data['name']}")
    print(f"   couples_count (минимальное): {data['couples_count']}")
    print(f"   set_format (общее количество пар): {data['set_format']}")
    print(f"   formation: {data['formation']}")
    print("---")
    
    return data
################

def format_dance_data_for_display(dance_data):
    """Форматирование данных для отображения"""
    return {
        'Название': dance_data.get('name', 'Неизвестно'),
        'Тип': dance_data.get('dance_type', 'Неизвестно'),
        'Размер': dance_data.get('meter', 'Неизвестно'),
        'Код тактов': dance_data.get('bars', 'Неизвестно'),
        'Количество тактов': dance_data.get('bars_count', 'Неизвестно'),
        'Автор': dance_data.get('author', 'Неизвестно'),
        'Год': dance_data.get('year', 'Неизвестно'),
        'Минимальное количество пар': f"{dance_data.get('couples_count', 4)} пары",
        'Формат сета': f"{dance_data.get('set_format', 4)} couples",  # ИСПРАВЛЕНО: "4 couples"
        'Тип сета': dance_data.get('formation', 'Longwise'),
        'Прогрессия': dance_data.get('progression', 'Неизвестно'),
        'Повторения': dance_data.get('repetitions', 4),
        'Интенсивность': dance_data.get('intensity', 'Неизвестно'),
        'Шаги': ', '.join(dance_data.get('steps', [])),
        'Публикации': ', '.join(dance_data.get('published_in', [])),
        'Музыка': ', '.join(dance_data.get('recommended_music', [])),
        'Формации': ', '.join(dance_data.get('formations_list', [])),
        'Фигур': len(dance_data.get('figures', [])),
        'Изображений': len(dance_data.get('images', [])),
        'Доп. информация': dance_data.get('extra_info', 'Отсутствует')[:100] + '...' 
            if dance_data.get('extra_info') else 'Отсутствует'
    }