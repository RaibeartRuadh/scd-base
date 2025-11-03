from flask import Blueprint, render_template, request, flash
from app import db, Dance, DanceType, DanceFormat, SetType
from sqlalchemy import and_, or_

search_bp = Blueprint('search', __name__, template_folder='templates')

def get_search_filters():
    """Получение данных для фильтров поиска"""
    return {
        'dance_types': DanceType.query.order_by(DanceType.name).all(),
        'dance_formats': DanceFormat.query.order_by(DanceFormat.name).all(),
        'set_types': SetType.query.order_by(SetType.name).all(),
        'dance_couples': db.session.query(Dance.dance_couple).distinct().filter(Dance.dance_couple.isnot(None)).order_by(Dance.dance_couple).all()
    }

def build_search_query(filters):
    """Построение запроса поиска с комбинацией условий И/ИЛИ"""
    query = Dance.query
    
    conditions = []
    
    # Поиск по имени (ИЛИ для нескольких слов)
    if filters.get('name'):
        name_terms = [term.strip() for term in filters['name'].split() if term.strip()]
        if name_terms:
            name_conditions = []
            for term in name_terms:
                name_conditions.append(Dance.name.ilike(f'%{term}%'))
            conditions.append(or_(*name_conditions))
    
    # Поиск по автору (ИЛИ для нескольких слов)
    if filters.get('author'):
        author_terms = [term.strip() for term in filters['author'].split() if term.strip()]
        if author_terms:
            author_conditions = []
            for term in author_terms:
                author_conditions.append(Dance.author.ilike(f'%{term}%'))
            conditions.append(or_(*author_conditions))
    
    # Поиск по типу танца (И для нескольких типов)
    if filters.get('dance_types'):
        dance_type_ids = [int(x) for x in filters['dance_types']]
        conditions.append(Dance.dance_type_id.in_(dance_type_ids))
    
    # Поиск по формату сета (И для нескольких форматов)
    if filters.get('dance_formats'):
        format_ids = [int(x) for x in filters['dance_formats']]
        conditions.append(Dance.dance_format_id.in_(format_ids))
    
    # Поиск по типу сета (И для нескольких типов)
    if filters.get('set_types'):
        set_type_ids = [int(x) for x in filters['set_types']]
        conditions.append(Dance.set_type_id.in_(set_type_ids))
    
    # Поиск по танцующим парам (И для нескольких значений)
    if filters.get('dance_couples'):
        couple_values = filters['dance_couples']
        conditions.append(Dance.dance_couple.in_(couple_values))
    
    # Поиск по публикации (ИЛИ для нескольких слов)
    if filters.get('published'):
        published_terms = [term.strip() for term in filters['published'].split() if term.strip()]
        if published_terms:
            published_conditions = []
            for term in published_terms:
                published_conditions.append(Dance.published.ilike(f'%{term}%'))
            conditions.append(or_(*published_conditions))
    
    # Поиск по повторам
    if filters.get('count_min'):
        try:
            conditions.append(Dance.count_id >= int(filters['count_min']))
        except (ValueError, TypeError):
            pass
    
    if filters.get('count_max'):
        try:
            conditions.append(Dance.count_id <= int(filters['count_max']))
        except (ValueError, TypeError):
            pass
    
    # Поиск по размеру (тактам)
    if filters.get('size_min'):
        try:
            conditions.append(Dance.size_id >= int(filters['size_min']))
        except (ValueError, TypeError):
            pass
    
    if filters.get('size_max'):
        try:
            conditions.append(Dance.size_id <= int(filters['size_max']))
        except (ValueError, TypeError):
            pass
    
    # Применяем все условия через И
    if conditions:
        query = query.filter(and_(*conditions))
    
    return query

@search_bp.route('/search', methods=['GET', 'POST'])
def advanced_search():
    """Расширенный поиск танцев"""
    filters = {}
    results = []
    total_count = 0
    
    if request.method == 'POST':
        try:
            # Собираем фильтры из формы
            filters = {
                'name': request.form.get('name', '').strip(),
                'author': request.form.get('author', '').strip(),
                'dance_types': request.form.getlist('dance_types'),
                'dance_formats': request.form.getlist('dance_formats'),
                'set_types': request.form.getlist('set_types'),
                'dance_couples': request.form.getlist('dance_couples'),
                'published': request.form.get('published', '').strip(),
                'count_min': request.form.get('count_min', '').strip(),
                'count_max': request.form.get('count_max', '').strip(),
                'size_min': request.form.get('size_min', '').strip(),
                'size_max': request.form.get('size_max', '').strip()
            }
            
            # Строим запрос
            query = build_search_query(filters)
            
            # Выполняем поиск
            results = query.order_by(Dance.name).all()
            total_count = len(results)
            
            if total_count == 0:
                flash('По вашему запросу ничего не найдено', 'info')
            else:
                flash(f'Найдено танцев: {total_count}', 'success')
                
        except Exception as e:
            flash(f'Ошибка при выполнении поиска: {str(e)}', 'danger')
    
    # Получаем данные для фильтров
    search_data = get_search_filters()
    search_data.update({
        'filters': filters,
        'results': results,
        'total_count': total_count
    })
    
    return render_template('search.html', **search_data)

@search_bp.route('/search/results')
def search_results():
    """Быстрый поиск (для использования из других страниц)"""
    query = request.args.get('q', '')
    if query:
        results = Dance.query.filter(
            or_(
                Dance.name.ilike(f'%{query}%'),
                Dance.author.ilike(f'%{query}%'),
                Dance.published.ilike(f'%{query}%')
            )
        ).order_by(Dance.name).all()
        
        return render_template('search_results.html', 
                             results=results, 
                             query=query, 
                             total_count=len(results))
    
    return redirect(url_for('search.advanced_search'))