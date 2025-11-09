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
        
        # Получаем оба описания
        descriptions = self._parse_description()
        
        data = {
            'name': self._parse_name(),
            'dance_type': main_info.get('dance_type', self._parse_dance_type_fallback()),
            'meter': self._parse_meter(),
            'bars': self._parse_bars(),
            'bars_count': main_info.get('bars_count', self._parse_bars_count()),
            'formation': main_info.get('formation', self._parse_formation_fallback()),
            'couples_count': main_info.get('couples_count', self._parse_couples_count_fallback()),
            'set_format': main_info.get('set_format', main_info.get('couples_count', 4)),
            'progression': self._parse_progression(),
            'repetitions': main_info.get('repetitions', self._parse_repetitions()),
            'author': self._parse_author(),
            'year': self._parse_year(),
            'description': descriptions['description'],  # MiniCribs
            'description2': descriptions['description2'],  # E-cribs
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
        
        # Формируем размер в формате "повторения×такты" (например "8×32")
        data['size'] = self._format_size(data.get('repetitions'), data.get('bars_count'))
        
        # Отладочная информация
        print("🎯 ФИНАЛЬНЫЙ РЕЗУЛЬТАТ ПАРСИНГА:")
        for key in ['name', 'dance_type', 'size', 'meter', 'bars_count', 'repetitions', 'couples_count', 'set_format', 'formation']:
            print(f"   {key}: {data[key]}")
        print("---")
        
        return data
    
    def _format_size(self, repetitions, bars_count):
        """Форматирование размера в формате 'повторения×такты'"""
        reps = repetitions or 4  # значение по умолчанию для повторений
        bars = bars_count or 32  # значение по умолчанию для тактов
        return f"{reps}×{bars}"
    
    def _parse_main_info_string(self):
        """Парсинг основной информационной строки типа 'Reel · 32 bars · 3 couples · Longwise - 4'"""
        result = {
            'couples_count': None,
            'set_format': None,
            'formation': None,
            'dance_type': None,
            'bars_count': None,
            'repetitions': None
        }
        
        print("🔍 Начинаем поиск основной информационной строки...")
        
        # СПОСОБ 1: Ищем основной информационный блок с классом lead
        lead_div = self.soup.find('div', class_='lead')
        if lead_div:
            text = lead_div.get_text().strip()
            print(f"✅ Найден div.lead: '{text}'")
            return self._analyze_info_text(text, result)
        
        # СПОСОБ 2: Ищем после заголовка h1
        h1 = self.soup.find('h1')
        if h1:
            # Ищем следующий элемент с классом lead или любой параграф
            next_elem = h1.find_next_sibling(['div', 'p'])
            if next_elem:
                text = next_elem.get_text().strip()
                if any(keyword in text for keyword in ['bars', 'couples', 'Longwise', 'Square', 'Reel', 'Jig']):
                    print(f"✅ Найден элемент после h1: '{text}'")
                    return self._analyze_info_text(text, result)
        
        # СПОСОБ 3: Ищем любой элемент с ключевыми словами
        elements = self.soup.find_all(['div', 'p', 'span'])
        for elem in elements:
            text = elem.get_text().strip()
            if (any(keyword in text for keyword in ['bars', 'couples', 'Longwise', 'Square', 'repetitions']) and 
                len(text) < 200):  # Ограничиваем длину чтобы не брать большие тексты
                print(f"✅ Найден подходящий элемент: '{text}'")
                return self._analyze_info_text(text, result)
        
        print("❌ Основная информационная строка не найдена")
        return result

    def _analyze_info_text(self, text, result):
        """Анализ текста информационной строки"""
        print(f"🎯 Анализируем строку: '{text}'")
        
        # 1. Ищем тип танца (Reel, Jig, etc) - в начале строки
        dance_types = ['Reel', 'Jig', 'Strathspey', 'March', 'Waltz', 'Polka', 'Hornpipe', 'Medley']
        for dance_type in dance_types:
            if dance_type in text:
                result['dance_type'] = dance_type
                print(f"✅ Найдено dance_type: {dance_type}")
                break
        
        # 2. Ищем количество тактов (32 bars)
        bars_match = re.search(r'(\d+)\s*bars?', text, re.IGNORECASE)
        if bars_match:
            result['bars_count'] = int(bars_match.group(1))
            print(f"✅ Найдено bars_count: {result['bars_count']}")
        
        # 3. Ищем количество пар (3 couples)
        couples_match = re.search(r'(\d+)\s+couples?', text, re.IGNORECASE)
        if couples_match:
            result['couples_count'] = int(couples_match.group(1))
            print(f"✅ Найдено couples_count: {result['couples_count']}")
        
        # 4. Ищем формацию и формат сета (Longwise - 4)
        # Сначала ищем полный формат "Longwise - 4"
        formation_match = re.search(r'(Longwise|Square|Triangular|Circular)\s*[–—\-]\s*(\d+)', text, re.IGNORECASE)
        if formation_match:
            formation_name = formation_match.group(1)
            set_format = int(formation_match.group(2))
            
            formation_mapping = {
                'Longwise': 'Longwise set',
                'Square': 'Square set', 
                'Triangular': 'Triangular set',
                'Circular': 'Circular set'
            }
            
            result['formation'] = formation_mapping.get(formation_name, 'Longwise set')
            result['set_format'] = set_format
            print(f"✅ Найдено formation: {result['formation']}, set_format: {result['set_format']}")
        else:
            # Если не нашли с форматом, ищем просто формацию
            for formation in ['Longwise', 'Square', 'Triangular', 'Circular']:
                if formation.lower() in text.lower():
                    formation_mapping = {
                        'Longwise': 'Longwise set',
                        'Square': 'Square set', 
                        'Triangular': 'Triangular set',
                        'Circular': 'Circular set'
                    }
                    result['formation'] = formation_mapping.get(formation, 'Longwise set')
                    print(f"✅ Найдено formation (без формата): {result['formation']}")
                    break
        
        # 5. Ищем количество повторений (Usual number of repetitions: 8)
        repetitions_patterns = [
            r'Usual number of repetitions:\s*(\d+)',
            r'repetitions:\s*(\d+)',
            r'Repetitions:\s*(\d+)',
            r'·\s*(\d+)\s*reps?',
            r'\((\d+)\s*reps?\)'
        ]
        
        for pattern in repetitions_patterns:
            rep_match = re.search(pattern, text, re.IGNORECASE)
            if rep_match:
                result['repetitions'] = int(rep_match.group(1))
                print(f"✅ Найдено repetitions: {result['repetitions']}")
                break
        
        # 6. Если нашли формацию но не нашли set_format, используем couples_count
        if result['formation'] and not result['set_format'] and result['couples_count']:
            result['set_format'] = result['couples_count']
            print(f"⚠️  set_format не найден, используем couples_count: {result['set_format']}")
        
        return result

    def _get_main_info_text(self):
        """Вспомогательный метод для получения текста основной информационной строки"""
        # Ищем основной информационный блок
        lead_div = self.soup.find('div', class_='lead')
        if lead_div:
            return lead_div.get_text().strip()
        
        # Ищем после h1
        h1 = self.soup.find('h1')
        if h1:
            next_elem = h1.find_next_sibling(['div', 'p'])
            if next_elem:
                return next_elem.get_text().strip()
        
        return None
    
    def _parse_name(self):
        """Парсинг названия танца"""
        title_element = self.soup.find('span', {'id': 'title'})
        return title_element.get_text().strip() if title_element else 'Неизвестный танец'
    
    def _parse_dance_type_fallback(self):
        """Резервный метод парсинга типа танца"""
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Dance' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    dance_text = dd.get_text().strip()
                    dance_types = ['Reel', 'Jig', 'Strathspey', 'March', 'Waltz', 'Polka']
                    for dance_type in dance_types:
                        if dance_type in dance_text:
                            return dance_type
        return 'Unknown'
    
    def _parse_meter(self):
        """Парсинг музыкального размера (4/4L, 3/4, etc)"""
        # Ищем в основной информационной строке
        text = self._get_main_info_text()
        if text:
            meter_match = re.search(r'(\d+/\d+[A-Z]*)', text)
            if meter_match:
                return meter_match.group(1)
        
        # Ищем в структурированных данных
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Meter' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    meter_text = dd.get_text().strip()
                    meter_match = re.search(r'(\d+/\d+[A-Z]*)', meter_text)
                    return meter_match.group(1) if meter_match else meter_text
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
    
    def _parse_formation_fallback(self):
        """Резервный метод парсинга формации"""
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Formation' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    formation_text = dd.get_text().strip()
                    formation_mapping = {
                        'Longwise': 'Longwise set',
                        'Square': 'Square set', 
                        'Triangular': 'Triangular set',
                        'Circular': 'Circular set'
                    }
                    for key in formation_mapping:
                        if key in formation_text:
                            return formation_mapping[key]
        return 'Longwise set'
    
    def _parse_couples_count_fallback(self):
        """Резервный метод парсинга количества пар"""
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'Couples' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    couples_text = dd.get_text().strip()
                    couples_match = re.search(r'(\d+)', couples_text)
                    if couples_match:
                        return int(couples_match.group(1))
        return 4
    
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
        # Сначала ищем в основной информационной строке
        text = self._get_main_info_text()
        if text:
            repetitions_patterns = [
                r'Usual number of repetitions:\s*(\d+)',
                r'repetitions:\s*(\d+)',
                r'Repetitions:\s*(\d+)',
                r'·\s*(\d+)\s*reps?',
                r'\((\d+)\s*reps?\)'
            ]
            
            for pattern in repetitions_patterns:
                rep_match = re.search(pattern, text, re.IGNORECASE)
                if rep_match:
                    repetitions = int(rep_match.group(1))
                    print(f"✅ Найдено repetitions в основной строке: {repetitions}")
                    return repetitions
        
        # Затем ищем в структурированных данных
        dt_elements = self.soup.find_all('dt', class_='col-sm-2 text-sm-end')
        for dt in dt_elements:
            if 'repetitions' in dt.get_text().lower():
                dd = dt.find_next_sibling('dd')
                if dd:
                    text = dd.get_text()
                    rep_match = re.search(r'(\d+)', text)
                    if rep_match:
                        repetitions = int(rep_match.group(1))
                        print(f"✅ Найдено repetitions в структуре: {repetitions}")
                        return repetitions
        
        print("⚠️  Повторения не найдены, используем значение по умолчанию: 4")
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
        """Парсинг описания - MiniCribs в description, E-cribs в description2"""
        description = None
        description2 = None
        
        print("🔍 Начинаем поиск описаний...")
        
        cribs_tab = self.soup.find('div', {'id': 'cribs'})
        if cribs_tab:
            print("✅ Найдена вкладка Cribs")
            
            # СПОСОБ 1: Ищем MiniCribs для description
            mini_cribs = cribs_tab.find('div', class_='minicribs')
            if mini_cribs:
                description_text = self._clean_minicribs_text(mini_cribs.get_text())
                if description_text:
                    print("✅ Найдено описание в MiniCribs")
                    description = description_text
                    # Логируем первые 100 символов для отладки
                    preview = description_text[:100] + "..." if len(description_text) > 100 else description_text
                    print(f"📝 MiniCribs preview: {preview}")
            else:
                print("❌ MiniCribs не найден в вкладке Cribs")
                
                # Альтернативный поиск MiniCribs
                mini_cribs_alt = cribs_tab.find('p', class_='minicribs')
                if mini_cribs_alt:
                    description_text = self._clean_minicribs_text(mini_cribs_alt.get_text())
                    if description_text:
                        print("✅ Найдено описание в альтернативном MiniCribs (p.minicribs)")
                        description = description_text
            
            # СПОСОБ 2: Ищем E-cribs для description2
            e_cribs = cribs_tab.find('div', class_='cribtext')
            if e_cribs:
                description2_text = self._clean_cribs_text(e_cribs.get_text())
                if description2_text:
                    print("✅ Найдено описание в E-cribs")
                    description2 = description2_text
                    # Логируем первые 100 символов для отладки
                    preview = description2_text[:100] + "..." if len(description2_text) > 100 else description2_text
                    print(f"📝 E-cribs preview: {preview}")
            else:
                print("❌ E-cribs не найден в вкладке Cribs")
                
                # Альтернативный поиск E-cribs
                e_cribs_alt = cribs_tab.find('div', class_='cribs')
                if e_cribs_alt:
                    description2_text = self._clean_cribs_text(e_cribs_alt.get_text())
                    if description2_text:
                        print("✅ Найдено описание в альтернативном E-cribs (div.cribs)")
                        description2 = description2_text
        
        else:
            print("❌ Вкладка Cribs не найдена, ищем описания в основном контенте")
        
        # СПОСОБ 3: Если не нашли в структурированной вкладке, ищем в основном блоке
        if not description and not description2:
            print("🔄 Поиск описаний в основном контенте...")
            crib_div = self.soup.find('div', class_='cribtext')
            if crib_div:
                description_text = self._clean_cribs_text(crib_div.get_text())
                if description_text:
                    print("✅ Найдено описание в основном блоке cribtext")
                    description = description_text
        
        # СПОСОБ 4: Ищем любые элементы с классом minicribs по всей странице
        if not description:
            print("🔄 Расширенный поиск MiniCribs по всей странице...")
            all_minicribs = self.soup.find_all(class_='minicribs')
            for minicrib in all_minicribs:
                description_text = self._clean_minicribs_text(minicrib.get_text())
                if description_text and len(description_text) > 10:  # Проверяем что текст не пустой
                    print("✅ Найдено описание в расширенном поиске MiniCribs")
                    description = description_text
                    break
        
        # СПОСОБ 5: Ищем по текстовым маркерам MiniCribs
        if not description:
            print("🔄 Поиск MiniCribs по текстовым маркерам...")
            # Ищем элементы, содержащие типичные маркеры MiniCribs
            potential_minicribs = self.soup.find_all(['div', 'p', 'span'])
            for elem in potential_minicribs:
                text = elem.get_text().strip()
                # MiniCribs обычно короткие и содержат номера тактов
                if (len(text) > 20 and len(text) < 500 and 
                    any(marker in text for marker in ['1-8', '1–8', '1—8', '9-16', '1.', '2.', 'Bars'])):
                    description_text = self._clean_minicribs_text(text)
                    if description_text:
                        print("✅ Найдено описание по текстовым маркерам MiniCribs")
                        description = description_text
                        break
        
        # Финальная проверка и логирование результатов
        print("📊 РЕЗУЛЬТАТЫ ПОИСКА ОПИСАНИЙ:")
        print(f"   MiniCribs (description): {'✅ НАЙДЕНО' if description else '❌ НЕ НАЙДЕНО'}")
        print(f"   E-cribs (description2): {'✅ НАЙДЕНО' if description2 else '❌ НЕ НАЙДЕНО'}")
        
        if description:
            print(f"   Длина MiniCribs: {len(description)} символов")
        if description2:
            print(f"   Длина E-cribs: {len(description2)} символов")
        
        return {
            'description': description,
            'description2': description2
        }

    def _clean_minicribs_text(self, text):
        """Очистка и форматирование текста MiniCribs - убираем лишние элементы"""
        if not text:
            return None
        
        # Убираем лишние пробелы и переносы в начале/конце
        text = text.strip()
        
        # Удаляем название танца (первая строка) и другие лишние элементы
        lines = text.split('\n')
        cleaned_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Пропускаем строки с названием танца (первая строка обычно содержит название)
            if i == 0 and (any(keyword in line for keyword in ['Lassies', 'Reel', 'Jig', 'Strathspey', 'March']) or
                           len(line) < 30):  # Короткие строки вероятно заголовки
                continue
                
            # Пропускаем строки с музыкальным размером (2/4L · R32)
            if '·' in line and any(keyword in line for keyword in ['R32', 'R40', 'R48', 'J32', 'J40', 'J48', 'S32', 'S40']):
                continue
                
            # Пропускаем заголовки типа "MiniCribs" и разделители
            if line in ['MiniCribs', '[-]', 'Submit Comment', 'Mini Crib']:
                continue
                
            # Пропускаем строки, которые явно не являются описанием шагов
            if line.startswith('http') or 'comment' in line.lower():
                continue
                
            # Пропускаем пустые строки после фильтрации
            if line:
                cleaned_lines.append(line)
        
        # Объединяем обратно
        text = '\n'.join(cleaned_lines)
        
        # Заменяем переносы после номеров тактов (1-8, 9-16, 1-, 2- и т.д.) на 2 пробела
        patterns = [
            r'(\d+\-\d+)\s*\n\s*',  # 1-8\n
            r'(\d+\-)\s*\n\s*',     # 1-\n
            r'(\d+\.)\s*\n\s*',     # 1.\n
            r'(\d+\))\s*\n\s*',     # 1)\n
            r'(Bars \d+\-\d+)\s*\n\s*',  # Bars 1-8\n
        ]
        
        for pattern in patterns:
            text = re.sub(pattern, r'\1  ', text)
        
        # Заменяем множественные переносы на одинарные
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Убираем лишние пробелы
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Убираем пробелы в начале и конце
        text = text.strip()
        
        # Проверяем, что остался содержательный текст
        if not text or len(text) < 10:
            return None
            
        return text

    def _clean_cribs_text(self, text):
        """Очистка и форматирование текста E-cribs"""
        if not text:
            return None
        
        # Убираем лишние пробелы и переносы в начале/конце
        text = text.strip()
        
        # Заменяем переносы после номеров тактов на 2 пробела
        patterns = [
            r'(\d+\-\d+)\s*\n\s*',  # 1-8\n
            r'(\d+\-)\s*\n\s*',     # 1-\n
            r'(\d+\.)\s*\n\s*',     # 1.\n
            r'(\d+\))\s*\n\s*',     # 1)\n
        ]
        
        for pattern in patterns:
            text = re.sub(pattern, r'\1  ', text)
        
        # Заменяем множественные переносы на одинарные
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Убираем лишние пробелы
        text = re.sub(r'[ \t]+', ' ', text)
        
        return text.strip()
    
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

    def _debug_cribs_structure(self):
        """Отладочный метод для анализа структуры вкладки Cribs"""
        cribs_tab = self.soup.find('div', {'id': 'cribs'})
        if not cribs_tab:
            print("❌ Вкладка Cribs не найдена для отладки")
            return
        
        print("🔍 ОТЛАДКА СТРУКТУРЫ CRIBS:")
        
        # Находим все дочерние элементы
        children = list(cribs_tab.children)
        print(f"   Всего дочерних элементов: {len(children)}")
        
        # Ищем все div с классами
        divs = cribs_tab.find_all('div')
        print(f"   Всего div элементов: {len(divs)}")
        
        for i, div in enumerate(divs):
            classes = div.get('class', [])
            text_preview = div.get_text()[:50].replace('\n', ' ') + "..." if div.get_text() else "ПУСТОЙ"
            print(f"   Div {i}: классы={classes}, текст={text_preview}")
        
        # Ищем все элементы с классом minicribs
        minicribs_elements = cribs_tab.find_all(class_='minicribs')
        print(f"   Элементов с классом minicribs: {len(minicribs_elements)}")
        
        for i, elem in enumerate(minicribs_elements):
            tag = elem.name
            text_preview = elem.get_text()[:100].replace('\n', ' ') + "..." if elem.get_text() else "ПУСТОЙ"
            print(f"   MiniCribs {i} ({tag}): {text_preview}")
        
        # Ищем все элементы с классом cribtext
        cribtext_elements = cribs_tab.find_all(class_='cribtext')
        print(f"   Элементов с классом cribtext: {len(cribtext_elements)}")
        
        for i, elem in enumerate(cribtext_elements):
            tag = elem.name
            text_preview = elem.get_text()[:100].replace('\n', ' ') + "..." if elem.get_text() else "ПУСТОЙ"
            print(f"   Cribtext {i} ({tag}): {text_preview}")


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


def format_dance_data_for_display(dance_data):
    """Форматирование данных для отображения"""
    return {
        'Название': dance_data.get('name', 'Неизвестно'),
        'Тип': dance_data.get('dance_type', 'Неизвестно'),
        'Размер': dance_data.get('size', 'Неизвестно'),
        'Музыкальный размер': dance_data.get('meter', 'Неизвестно'),
        'Код тактов': dance_data.get('bars', 'Неизвестно'),
        'Количество тактов': dance_data.get('bars_count', 'Неизвестно'),
        'Повторения': dance_data.get('repetitions', 'Неизвестно'),
        'Автор': dance_data.get('author', 'Неизвестно'),
        'Год': dance_data.get('year', 'Неизвестно'),
        'Минимальное количество пар': f"{dance_data.get('couples_count', 4)} пары",
        'Формат сета': f"{dance_data.get('set_format', 4)} couples",
        'Тип сета': dance_data.get('formation', 'Longwise'),
        'Прогрессия': dance_data.get('progression', 'Неизвестно'),
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