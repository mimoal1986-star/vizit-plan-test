# Картография
try:
    import folium
    from streamlit_folium import folium_static
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False
    # st.sidebar.warning("⚠️ Для карты установите: pip install folium streamlit-folium")
import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, date, timedelta
import calendar
import json
import base64
from typing import Dict, List, Tuple, Optional, Any
import warnings
warnings.filterwarnings('ignore')

# ВИЗУАЛИЗАЦИЯ
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ГЕОМЕТРИЯ - всегда используем упрощенную версию
SCIPY_AVAILABLE = False
try:
    # Пробуем импортировать scipy
    import scipy
    # Проверяем, можем ли мы использовать ConvexHull
    from scipy.spatial import ConvexHull
    SCIPY_AVAILABLE = True
    st.sidebar.success("✅ SciPy доступен")
except:
    SCIPY_AVAILABLE = False
    st.sidebar.info("ℹ️ Используется упрощенная генерация полигонов")

# НАСТРОЙКА СТРАНИЦЫ
st.set_page_config(
    page_title="Калькулятор плана визитов",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Калькулятор плана визитов по сотрудникам")
st.markdown("---")

# ==============================================
# ИНИЦИАЛИЗАЦИЯ SESSION STATE
# ==============================================

if 'points_df' not in st.session_state:
    st.session_state.points_df = None
if 'auditors_df' not in st.session_state:
    st.session_state.auditors_df = None
if 'visits_df' not in st.session_state:
    st.session_state.visits_df = None
if 'summary_df' not in st.session_state:
    st.session_state.summary_df = None
if 'details_df' not in st.session_state:
    st.session_state.details_df = None
if 'city_stats_df' not in st.session_state:
    st.session_state.city_stats_df = None
if 'type_stats_df' not in st.session_state:
    st.session_state.type_stats_df = None
if 'polygons' not in st.session_state:
    st.session_state.polygons = None
if 'plan_calculated' not in st.session_state:
    st.session_state.plan_calculated = False
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'plan_partial' not in st.session_state:
    st.session_state.plan_partial = False

# ==============================================
# БОКОВАЯ ПАНЕЛЬ - НАСТРОЙКИ
# ==============================================

with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Выбор квартала и года
    col1, col2 = st.columns(2)
    with col1:
        quarter = st.selectbox("Квартал", [1, 2, 3, 4], index=0, key="sidebar_quarter")
    with col2:
        year = st.selectbox("Год", list(range(2023, 2027)), index=2, key="sidebar_year")
    
    # Коэффициенты этапов
    st.subheader("Коэффициенты нагрузки по этапам")
    st.caption("Квартал делится на 4 этапа")
    
    stage1 = st.number_input("Этап 1 коэффициент", value=0.8, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage1")
    stage2 = st.number_input("Этап 2 коэффициент", value=1.0, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage2")
    stage3 = st.number_input("Этап 3 коэффициент", value=1.2, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage3")
    stage4 = st.number_input("Этап 4 коэффициент", value=0.9, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage4")
    
    coefficients = [stage1, stage2, stage3, stage4]
    
    st.markdown("---")
    
    st.info("""
    **Инструкция:**
    1. Загрузите файл с данными (1 файл, 3 вкладки)
    2. Настройте квартал и коэффициенты
    3. Нажмите кнопку "Рассчитать план"
    4. Используйте вкладки для анализа
    
    *Настройки сохраняются автоматически*
    """)

# ==============================================
# ФУНКЦИИ ДЛЯ СОЗДАНИЯ ШАБЛОНОВ
# ==============================================

def create_template_points():
    """Создает шаблон для файла Точки"""
    data = {
        'ID_Точки': ['P001', 'P002', 'P003', 'P004'],
        'Название_Точки': ['Магазин 1', 'Гипермаркет 1', 'Супермаркет 1', 'Минимаркет 2'],
        'Адрес': ['ул. Ленина, 1', 'ул. Мира, 10', 'пр. Победы, 5', 'ул. Центральная, 3'],
        'Широта': [55.7558, 55.7507, 55.7601, 55.7520],
        'Долгота': [37.6173, 37.6177, 37.6254, 37.6200],
        'Город': ['Москва', 'Москва', 'Москва', 'Москва'],
        'Тип': ['Convenience', 'Hypermarket', 'Supermarket', 'Convenience'],
        'Кол-во_посещений': [1, 1, 1, 2]
    }
    return pd.DataFrame(data)

def create_template_auditors():
    """Создает шаблон для файла Аудиторы"""
    data = {
        'ID_Сотрудника': ['SOVIAUD10', 'SOVIAUD11', 'SOVIAUD12'],
        'Город': ['Москва', 'Москва', 'Санкт-Петербург']
    }
    return pd.DataFrame(data)

def create_template_visits():
    """Создает шаблон для файла Факт_посещений"""
    data = {
        'ID_Точки': ['P001', 'P001', 'P002'],
        'Дата_визита': ['15.04.2025', '30.04.2025', '16.04.2025'],
        'ID_Сотрудника': ['SOVIAUD10', 'SOVIAUD10', 'SOVIAUD11']
    }
    return pd.DataFrame(data)

# ==============================================
# ФУНКЦИИ ДЛЯ СКАЧИВАНИЯ ФАЙЛОВ
# ==============================================

def get_download_link(data, filename, text, mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
    """Генерирует ссылку для скачивания файла"""
    b64 = base64.b64encode(data).decode()
    href = f'<a href="data:{mime_type};base64,{b64}" download="{filename}">{text}</a>'
    return href

# ==============================================
# ФУНКЦИИ ДЛЯ ОБРАБОТКИ ДАННЫХ
# ==============================================

def load_and_process_data(file):
    """Загружает и обрабатывает файл с тремя вкладками"""
    try:
        # Читаем все три вкладки
        points_df = pd.read_excel(file, sheet_name='Точки')
        auditors_df = pd.read_excel(file, sheet_name='Аудиторы')
        
        # Для факта посещений может быть пустая вкладка
        try:
            visits_df = pd.read_excel(file, sheet_name='Факт_посещений')
        except:
            visits_df = pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])
        
        return points_df, auditors_df, visits_df
        
    except Exception as e:
        st.error(f"❌ Ошибка при загрузке файла: {str(e)}")
        return None, None, None

def load_and_process_points(df):
    """Обрабатывает данные из вкладки Точки"""
    try:
        # Копируем DataFrame чтобы не изменять оригинал
        points_df = df.copy()
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Точки', 'Широта', 'Долгота', 'Город', 'Тип']
        missing_cols = [col for col in required_cols if col not in points_df.columns]
        
        if missing_cols:
            # Попробуем найти альтернативные названия
            column_mapping = {
                'ID_Точки': ['ID точки', 'ID_точки', 'Point_ID'],
                'Широта': ['Latitude', 'Lat', 'широта'],
                'Долгота': ['Longitude', 'Lon', 'долгота'],
                'Город': ['City', 'city', 'Город работы'],
                'Тип': ['Type', 'Category', 'Тип точки']
            }
            
            for required_col in missing_cols:
                if required_col in column_mapping:
                    for alt_name in column_mapping[required_col]:
                        if alt_name in points_df.columns and required_col not in points_df.columns:
                            points_df = points_df.rename(columns={alt_name: required_col})
                            break
        
        # Проверяем еще раз
        missing_cols = [col for col in required_cols if col not in points_df.columns]
        if missing_cols:
            st.error(f"❌ В файле Точки отсутствуют обязательные колонки: {', '.join(missing_cols)}")
            return None
        
        # Конвертируем типы точек
        type_mapping = {
            'Convenience': 'Мини',
            'convenience': 'Мини',
            'Convenience Store': 'Мини',
            'Convenience store': 'Мини',
            'Hypermarket': 'Гипер',
            'hypermarket': 'Гипер',
            'Supermarket': 'Супер',
            'supermarket': 'Супер',
            'Мини': 'Мини',
            'Гипер': 'Гипер',
            'Супер': 'Супер'
        }
        
        if 'Тип' in points_df.columns:
            points_df['Тип'] = points_df['Тип'].map(type_mapping).fillna('Мини')
        
        # Обрабатываем количество посещений
        if 'Кол-во_посещений' in points_df.columns:
            points_df['Кол-во_посещений'] = pd.to_numeric(points_df['Кол-во_посещений'], errors='coerce').fillna(1).astype(int)
        else:
            points_df['Кол-во_посещений'] = 1
        
        # Добавляем недостающие колонки
        if 'Название_Точки' not in points_df.columns:
            points_df['Название_Точки'] = points_df['ID_Точки']
        if 'Адрес' not in points_df.columns:
            points_df['Адрес'] = ''
        
        # Валидация координат
        valid_coords = points_df[
            (points_df['Широта'] >= 41) & (points_df['Широта'] <= 82) &
            (points_df['Долгота'] >= 19) & (points_df['Долгота'] <= 180)
        ]
        
        invalid_coords = points_df[~points_df.index.isin(valid_coords.index)]
        if len(invalid_coords) > 0:
            st.warning(f"⚠️ Пропущено {len(invalid_coords)} точек с некорректными координатами (только Россия: широта 41-82, долгота 19-180)")
        
        if len(valid_coords) == 0:
            st.error("❌ Нет точек с корректными координатами")
            return None
        
        return valid_coords.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке данных Точки: {str(e)}")
        return None

def load_and_process_auditors(df):
    """Обрабатывает данные из вкладки Аудиторы"""
    try:
        # Копируем DataFrame
        auditors_df = df.copy()
        
        # Стандартизируем названия колонок
        column_mapping = {
            'ID_Сотрудника': ['ID Сотрудника', 'ID_сотрудника', 'Employee_ID', 'employee_id', 'Сотрудник'],
            'Город': ['City', 'city', 'Город работы']
        }
        
        for target_col, alt_names in column_mapping.items():
            if target_col not in auditors_df.columns:
                for alt_name in alt_names:
                    if alt_name in auditors_df.columns:
                        auditors_df = auditors_df.rename(columns={alt_name: target_col})
                        break
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Сотрудника', 'Город']
        missing_cols = [col for col in required_cols if col not in auditors_df.columns]
        
        if missing_cols:
            st.error(f"❌ В файле Аудиторы отсутствуют обязательные колонки: {', '.join(missing_cols)}")
            return None
        
        return auditors_df
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке данных Аудиторы: {str(e)}")
        return None

def load_and_process_visits(df):
    """Обрабатывает данные из вкладки Факт_посещений"""
    try:
        if df.empty:
            return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])
        
        # Копируем DataFrame
        visits_df = df.copy()
        
        # Стандартизируем названия колонок
        column_mapping = {
            'ID_Точки': ['ID точки', 'ID_точки', 'Point_ID'],
            'Дата_визита': ['Дата визита', 'Дата', 'Date', 'Visit Date', 'Дата посещения'],
            'ID_Сотрудника': ['ID Сотрудника', 'ID_сотрудника', 'Employee_ID', 'Сотрудник']
        }
        
        for target_col, alt_names in column_mapping.items():
            if target_col not in visits_df.columns:
                for alt_name in alt_names:
                    if alt_name in visits_df.columns:
                        visits_df = visits_df.rename(columns={alt_name: target_col})
                        break
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Точки', 'Дата_визита', 'ID_Сотрудника']
        missing_cols = [col for col in required_cols if col not in visits_df.columns]
        
        if missing_cols:
            st.warning(f"⚠️ В файле Факт_посещений отсутствуют колонки: {', '.join(missing_cols)}")
            return pd.DataFrame(columns=required_cols)
        
        # Преобразуем даты (пробуем разные форматы)
        date_formats = ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y/%m/%d']
        
        for date_format in date_formats:
            try:
                visits_df['Дата_визита'] = pd.to_datetime(visits_df['Дата_визита'], format=date_format, errors='raise')
                break
            except:
                continue
        else:
            # Если ни один формат не подошел, пробуем автоопределение
            visits_df['Дата_визита'] = pd.to_datetime(visits_df['Дата_визита'], errors='coerce')
        
        # Удаляем строки с невалидными датами
        invalid_dates = visits_df['Дата_визита'].isna().sum()
        if invalid_dates > 0:
            st.warning(f"⚠️ Пропущено {invalid_dates} записей с невалидными датами")
        
        visits_df = visits_df.dropna(subset=['Дата_визита'])
        
        return visits_df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке данных Факт_посещений: {str(e)}")
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])

# ==============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ДАТАМИ И НЕДЕЛЯМИ
# ==============================================

def get_quarter_dates(year, quarter):
    """Возвращает даты начала и конца квартала"""
    quarter_starts = [date(year, 1, 1), date(year, 4, 1), date(year, 7, 1), date(year, 10, 1)]
    quarter_start = quarter_starts[quarter - 1]
    
    if quarter == 4:
        quarter_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        quarter_end = quarter_starts[quarter] - timedelta(days=1)
    
    return quarter_start, quarter_end

def get_iso_week(date_obj):
    """Возвращает ISO номер недели для даты"""
    return date_obj.isocalendar()[1]

def get_weeks_in_quarter(year, quarter):
    """Возвращает список недель в квартале с ISO номерами"""
    quarter_start, quarter_end = get_quarter_dates(year, quarter)
    
    weeks = []
    current_date = quarter_start
    
    while current_date <= quarter_end:
        week_start = current_date
        week_end = min(current_date + timedelta(days=6), quarter_end)
        
        iso_week = get_iso_week(week_start)
        
        weeks.append({
            'iso_week_number': iso_week,
            'start_date': week_start,
            'end_date': week_end,
            'week_display': f"Неделя {iso_week} ({week_start.strftime('%d.%m')}-{week_end.strftime('%d.%m')})"
        })
        
        current_date = week_end + timedelta(days=1)
    
    return weeks

# ==============================================
# ФУНКЦИИ ДЛЯ ГЕНЕРАЦИИ ПОЛИГОНОВ И РАСПРЕДЕЛЕНИЯ
# ==============================================

def create_simple_polygon(points):
    """Создает простой полигон (прямоугольник) без SciPy"""
    if len(points) == 0:
        return []
    
    # ИСПРАВЛЕНИЕ: безопасное извлечение координат из разных форматов
    coords = []
    
    if isinstance(points, np.ndarray):
        # Формат numpy array
        if points.ndim == 2 and points.shape[1] >= 3:
            # Предполагаем формат: [ID, широта, долгота, ...]
            for point in points:
                if len(point) >= 3:
                    try:
                        lat = float(point[1])
                        lon = float(point[2])
                        coords.append([lat, lon])
                    except (ValueError, TypeError, IndexError):
                        continue
    else:
        # Формат списка/кортежа
        for point in points:
            if isinstance(point, (list, tuple, np.ndarray)) and len(point) >= 3:
                try:
                    # Формат: [ID, широта, долгота]
                    lat = float(point[1])
                    lon = float(point[2])
                    coords.append([lat, lon])
                except (ValueError, TypeError, IndexError):
                    continue
    
    # ИСПРАВЛЕНИЕ: если не удалось извлечь координаты
    if not coords:
        return []
    
    if len(coords) == 1:
        # Одна точка - возвращаем пустой список
        return []
    elif len(coords) == 2:
        # Две точки - создаем линию
        return [coords[0], coords[1], coords[0]]
    else:
        # Несколько точек - создаем bounding box
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        # Создаем прямоугольник
        polygon = [
            [min_lat, min_lon],  # нижний левый
            [min_lat, max_lon],  # нижний правый
            [max_lat, max_lon],  # верхний правый
            [max_lat, min_lon],  # верхний левый
            [min_lat, min_lon]   # замыкаем полигон
        ]

        return polygon

def generate_polygons(polygons_info):
    """Генерирует полигоны на основе информации о точках"""
    polygons = {}
    
    if not polygons_info or not isinstance(polygons_info, dict):
        return {}
    
    try:
        for polygon_name, info in polygons_info.items():
            if not info or not isinstance(info, dict) or 'points' not in info:
                continue
                
            points = np.array(info['points'])
            
            if len(points) == 0:
                polygons[polygon_name] = {
                    'auditor': info.get('auditor', 'Неизвестно'),
                    'city': info.get('city', 'Неизвестно'),  # ← ДОБАВЛЕНО
                    'coordinates': [],
                    'points_count': 0,
                    'points': []
                }
                continue
                
            if len(points) < 2:
                polygons[polygon_name] = {
                    'auditor': info.get('auditor', 'Неизвестно'),
                    'city': info.get('city', 'Неизвестно'),  # ← ДОБАВЛЕНО
                    'coordinates': [],
                    'points_count': len(points),
                    'points': points.tolist()  # ← ДОБАВЛЕНО
                }
                continue
            
            polygon_coords = create_simple_polygon(points)
            
            polygons[polygon_name] = {
                'auditor': info['auditor'],
                'city': info.get('city', polygon_name.split('-')[0]),  # ← ДОБАВЛЕНО
                'coordinates': polygon_coords,
                'points_count': len(points),
                'points': points.tolist()  # ← ДОБАВЛЕНО
            }
        
        return polygons
    except Exception as e:
        st.error(f"❌ Ошибка при генерации полигонов: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")
        return {}

# ==============================================
# ФУНКЦИИ ДЛЯ РАСПРЕДЕЛЕНИЯ ПО НЕДЕЛЯМ
# ==============================================

def distribute_visits_by_weeks(points_assignment_df, points_df, year, quarter, coefficients):
    """Распределяет посещения по неделям на основе личных планов аудиторов"""
    try:
        # 1. Получаем недели в квартале
        weeks_info = get_weeks_in_quarter(year, quarter)
        if not weeks_info:
            return pd.DataFrame()
        
        # 2. Объединяем точки с их аудиторами и планом посещений
        merged_df = pd.merge(
            points_df[['ID_Точки', 'Кол-во_посещений', 'Город']],
            points_assignment_df[['ID_Точки', 'Аудитор', 'Полигон']],
            on='ID_Точки',
            how='left'
        )
        
        # 3. Рассчитываем личный план каждого аудитора
        auditor_plans = merged_df.groupby(['Город', 'Аудитор', 'Полигон'])['Кол-во_посещений'].sum().reset_index()
        auditor_plans = auditor_plans.rename(columns={'Кол-во_посещений': 'Личный_план'})
        
        # 4. Распределяем каждый личный план по неделям
        weekly_plan = []
        
        for _, auditor_row in auditor_plans.iterrows():
            city = auditor_row['Город']
            auditor = auditor_row['Аудитор']
            polygon = auditor_row['Полигон']
            personal_plan = auditor_row['Личный_план']
            
            if personal_plan <= 0:
                continue
            
            # 5. Распределяем личный план аудитора по неделям с учетом коэффициентов
            weeks_in_quarter = len(weeks_info)
            
            # Базовая нагрузка по неделям (равномерно)
            base_per_week = max(1, personal_plan // weeks_in_quarter)
            
            for week_info in weeks_info:
                iso_week = week_info['iso_week_number']
                week_index = (iso_week - 1) % 4  # Для коэффициентов (0-3)
                
                # Применяем коэффициент
                coefficient = coefficients[week_index % len(coefficients)]
                weekly_visits = int(round(base_per_week * coefficient))
                
                # Минимум 0 посещений
                weekly_visits = max(0, weekly_visits)
                
                if weekly_visits > 0:
                    weekly_plan.append({
                        'Город': city,
                        'Полигон': polygon,
                        'Аудитор': auditor,
                        'ISO_Неделя': iso_week,
                        'Дата_начала': week_info['start_date'],
                        'Дата_окончания': week_info['end_date'],
                        'План_посещений': weekly_visits
                    })
        
        # 6. Создаем DataFrame и корректируем округления
        result_df = pd.DataFrame(weekly_plan)
        
        if not result_df.empty:
            # Группируем по аудиторам и перераспределяем остаток
            for (city, auditor), group in result_df.groupby(['Город', 'Аудитор']):
                # Находим целевой личный план
                target_plan = auditor_plans[
                    (auditor_plans['Город'] == city) & 
                    (auditor_plans['Аудитор'] == auditor)
                ]['Личный_план'].sum()
                
                # Находим текущую сумму в распределении
                current_sum = group['План_посещений'].sum()
                
                # Корректируем разницу
                difference = target_plan - current_sum
                
                if difference != 0:
                    # Добавляем/убираем разницу у первой недели этого аудитора
                    first_week_idx = result_df[
                        (result_df['Город'] == city) & 
                        (result_df['Аудитор'] == auditor)
                    ].index[0]
                    
                    new_value = result_df.at[first_week_idx, 'План_посещений'] + difference
                    result_df.at[first_week_idx, 'План_посещений'] = max(0, new_value)
        
        # 7. Проверяем итоговую сумму
        total_expected = points_df['Кол-во_посещений'].sum()
        total_distributed = result_df['План_посещений'].sum()
        
        if total_expected != total_distributed:
            st.warning(f"⚠️ Небольшое расхождение в распределении: {total_expected} ≠ {total_distributed}")
            # Корректируем у первого аудитора
            if not result_df.empty:
                result_df.iloc[0, result_df.columns.get_loc('План_посещений')] += (total_expected - total_distributed)
        
        return result_df
        
    except Exception as e:
        import traceback
        st.error(f"❌ Ошибка при распределении посещений по неделям: {str(e)}")
        st.error(f"Детали:\n{traceback.format_exc()}")
        return pd.DataFrame()

# ==============================================
# ФУНКЦИИ ДЛЯ РАСПРЕДЕЛЕНИЯ ПО АУДИТОРАМ
# ==============================================

def distribute_points_to_auditors(points_df, auditors_df):
    """Распределяет точки по аудиторам внутри каждого города"""
    
    if points_df is None or points_df.empty:
        st.error("❌ Нет данных о точках для распределения")
        return None, None
    
    results = []
    polygons_info = {}
    
    # Группируем по городам
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city].copy()
        city_auditors = auditors_df[auditors_df['Город'] == city]['ID_Сотрудника'].tolist()
        
        if len(city_auditors) == 0:
            st.warning(f"⚠️ В городе {city} нет аудиторов")
            continue
        
        if len(city_auditors) == 1:
            # Один аудитор - все точки ему
            auditor = city_auditors[0]
            for _, point in city_points.iterrows():
                results.append({
                    'ID_Точки': point['ID_Точки'],
                    'Аудитор': auditor,
                    'Город': city,
                    'Полигон': city
                })
            
            # Создаем полигон для одного аудитора
            polygons_info[f"{city}"] = {
                'auditor': auditor,
                'city': city,  # ← ДОБАВЛЕНО
                'points': city_points[['ID_Точки', 'Широта', 'Долгота']].values.tolist()
            }
            
        else:
            # Несколько аудиторов - делим точки
            city_points = city_points.sort_values('Долгота').reset_index(drop=True)
            
            directions = ['Запад', 'Центр', 'Восток', 'Север', 'Юг', 
                         'Северо-Запад', 'Северо-Восток', 'Юго-Запад', 'Юго-Восток']
            
            n = len(city_auditors)
            chunk_size = len(city_points) // n
            
            for i, auditor in enumerate(city_auditors):
                start_idx = i * chunk_size
                if i == n - 1:
                    end_idx = len(city_points)
                else:
                    end_idx = (i + 1) * chunk_size
                
                auditor_points = city_points.iloc[start_idx:end_idx]
                
                if len(auditor_points) == 0:
                    st.warning(f"⚠️ Аудитор {auditor} в городе {city} не получил точек")
                    continue
                
                polygon_name = f"{city}-{directions[i % len(directions)]}"
                for _, point in auditor_points.iterrows():
                    results.append({
                        'ID_Точки': point['ID_Точки'],
                        'Аудитор': auditor,
                        'Город': city,
                        'Полигон': polygon_name
                    })
                
                polygons_info[polygon_name] = {
                    'auditor': auditor,
                    'city': city,  # ← ДОБАВЛЕНО
                    'points': auditor_points[['ID_Точки', 'Широта', 'Долгота']].values.tolist()
                }
    
    if not results:
        st.warning("⚠️ Не удалось распределить точки по аудиторам (нет подходящих городов)")
        return None, None
    
    return pd.DataFrame(results), polygons_info

# ==============================================
# ФУНКЦИИ ДЛЯ ОБРАБОТКИ ФАКТИЧЕСКИХ ПОСЕЩЕНИЙ И СТАТИСТИКИ
# ==============================================

def process_actual_visits(visits_df, points_df, year, quarter):
    """Обрабатывает фактические посещения за квартал"""
    
    if visits_df.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника', 'ISO_Неделя'])
    
    # Получаем даты квартала
    quarter_start, quarter_end = get_quarter_dates(year, quarter)
    
    # Преобразуем даты для сравнения
    # ИСПРАВЛЕНИЕ: используем уже импортированный datetime
    quarter_start_dt = pd.Timestamp(datetime.combine(quarter_start, datetime.min.time()))
    quarter_end_dt = pd.Timestamp(datetime.combine(quarter_end, datetime.max.time()))
    
    # Фильтруем посещения по кварталу
    visits_in_quarter = visits_df[
        (visits_df['Дата_визита'] >= quarter_start_dt) &
        (visits_df['Дата_визита'] <= quarter_end_dt)
    ].copy()
    
    if visits_in_quarter.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника', 'ISO_Неделя'])
    
    # Добавляем ISO неделю
    visits_in_quarter['ISO_Неделя'] = visits_in_quarter['Дата_визита'].apply(get_iso_week)
    
    # Проверяем соответствие точек (только те, что есть в файле Точки)
    valid_point_ids = set(points_df['ID_Точки'].unique())
    invalid_visits = visits_in_quarter[~visits_in_quarter['ID_Точки'].isin(valid_point_ids)]
    
    if len(invalid_visits) > 0:
        st.warning(f"⚠️ Найдено {len(invalid_visits)} посещений несуществующих точек")
    
    # Оставляем только валидные посещения
    visits_in_quarter = visits_in_quarter[visits_in_quarter['ID_Точки'].isin(valid_point_ids)]
    
    return visits_in_quarter.reset_index(drop=True)

def calculate_statistics(points_df, visits_df, detailed_plan_df, year, quarter):
    """Минимальная версия - только самое необходимое"""
    
    # 1. Статистика по городам
    city_stats = []
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city]
        city_stats.append({
            'Город': city,
            'Всего_точек': len(city_points),
            'План_посещений': city_points['Кол-во_посещений'].sum(),
            'Факт_посещений': 0,
            '%_выполнения': 0.0
        })
    
    # 2. Статистика по типам
    type_stats = []
    for point_type in points_df['Тип'].unique():
        type_points = points_df[points_df['Тип'] == point_type]
        type_stats.append({
            'Тип': point_type,
            'План_посещений': type_points['Кол-во_посещений'].sum(),
            'Факт_посещений': 0,
            '%_выполнения': 0.0
        })
    
    # 3. Сводный план = detailed_plan_df (уже распределен по неделям и аудиторам)
    summary_df = detailed_plan_df.copy()
    
    # Добавляем недостающие колонки
    if 'Факт_посещений' not in summary_df.columns:
        summary_df['Факт_посещений'] = 0
    
    if '%_выполнения' not in summary_df.columns:
        summary_df['%_выполнения'] = 0.0
    
    # 4. Детализация = та же detailed_plan_df
    detailed_with_fact = detailed_plan_df.copy()
    
    # Проверка
    total_expected = points_df['Кол-во_посещений'].sum()
    total_in_summary = summary_df['План_посещений'].sum()
    
    if total_expected != total_in_summary:
        st.warning(f"⚠️ Расхождение: {total_expected} ≠ {total_in_summary}")
    
    return (
        pd.DataFrame(city_stats),
        pd.DataFrame(type_stats),
        summary_df,
        detailed_with_fact
    )

def create_google_maps_excel(points_df, polygons, points_assignment_df=None):
    """Создает Excel файл для импорта в Google Maps с разбиением по городам/полигонам"""
    
    excel_buffer = io.BytesIO()
    
    # Создаем словарь для сопоставления точек
    point_to_polygon = {}
    point_to_auditor = {}
    
    # 1. Используем points_assignment_df
    if points_assignment_df is not None and not points_assignment_df.empty:
        for idx, row in points_assignment_df.iterrows():
            try:
                point_id = str(row['ID_Точки']).strip()
                if point_id:
                    point_to_polygon[point_id] = row.get('Полигон', 'Не назначен')
                    point_to_auditor[point_id] = row.get('Аудитор', 'Неизвестно')
            except (KeyError, AttributeError):
                continue
    
    # 2. Если нет assignment_df, используем полигоны
    if not point_to_polygon and polygons:
        for poly_name, poly_info in polygons.items():
            if 'points' in poly_info and poly_info['points']:
                for point_info in poly_info['points']:
                    if point_info and len(point_info) >= 3:
                        try:
                            point_id = str(point_info[0]).strip() if point_info[0] is not None else ''
                            if point_id:
                                point_to_polygon[point_id] = poly_name
                                point_to_auditor[point_id] = poly_info.get('auditor', 'Неизвестно')
                        except (IndexError, AttributeError):
                            continue
    
    # 3. Подготавливаем данные с группировкой
    grouped_data = {}
    
    for idx, point in points_df.iterrows():
        try:
            # ID точки
            point_id_raw = point.get('ID_Точки', '')
            point_id_str = str(point_id_raw).strip() if point_id_raw is not None else ''
            
            if not point_id_str:
                continue
                
            # Полигон и аудитор
            polygon = point_to_polygon.get(point_id_str, 'Не назначен')
            auditor = point_to_auditor.get(point_id_str, 'Неизвестно')
            
            # Город точки
            city = point.get('Город', 'Неизвестно')
            if pd.isna(city):
                city = 'Неизвестно'
            
            # Определяем ключ для группировки
            group_key = city
            
            # Координаты
            lat_raw = point.get('Широта', 0)
            lon_raw = point.get('Долгота', 0)
            
            # Преобразуем координаты с ТОЧКОЙ как десятичным разделителем
            try:
                if isinstance(lat_raw, str):
                    lat_clean = lat_raw.replace(',', '.').strip()
                else:
                    lat_clean = str(lat_raw).replace(',', '.').strip()
                    
                if isinstance(lon_raw, str):
                    lon_clean = lon_raw.replace(',', '.').strip()
                else:
                    lon_clean = str(lon_raw).replace(',', '.').strip()
                
                lat_float = float(lat_clean)
                lon_float = float(lon_clean)
                
                lat = f"{lat_float:.6f}"
                lon = f"{lon_float:.6f}"
                
            except (ValueError, TypeError):
                lat = str(lat_raw).replace(',', '.').strip()
                lon = str(lon_raw).replace(',', '.').strip()
            
            # Название и тип точки
            point_name = point.get('Название_Точки', point_id_str)
            if pd.isna(point_name):
                point_name = point_id_str
            
            point_type = point.get('Тип', 'Неизвестно')
            if pd.isna(point_type):
                point_type = 'Неизвестно'
            
            # Добавляем точку в соответствующую группу
            if group_key not in grouped_data:
                grouped_data[group_key] = []
            
            grouped_data[group_key].append({
                'ID точки': point_id_str,
                'Имя точки': str(point_name),
                'Тип точки': str(point_type),
                'Город': str(city),
                'Полигон': str(polygon),
                'Аудитор': str(auditor),
                'Широта': lat,
                'Долгота': lon
            })
        except Exception as e:
            continue
    
    # 4. Проверяем общее количество строк
    total_rows = sum(len(points) for points in grouped_data.values())
    
    # Храним информацию о вкладках для сводки
    sheet_info = []
    
    # 5. Создаем Excel файл
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        sheet_counter = 0
        
        # Если строк меньше 2000 - создаем одну вкладку
        if total_rows <= 2000:
            # Объединяем все данные
            all_data = []
            for city, points in grouped_data.items():
                all_data.extend(points)
            
            if all_data:
                df_all = pd.DataFrame(all_data)
                column_order = ['ID точки', 'Имя точки', 'Тип точки', 'Город', 'Полигон', 'Аудитор', 'Широта', 'Долгота']
                column_order = [col for col in column_order if col in df_all.columns]
                df_all = df_all[column_order]
                
                sheet_name = 'Все точки'
                df_all.to_excel(writer, sheet_name=sheet_name, index=False)
                
                sheet_info.append({
                    'Вкладка': sheet_name,
                    'Количество точек': len(df_all),
                    'Город': 'Все',
                    'Полигон': 'Все',
                    'Аудиторов': df_all['Аудитор'].nunique()
                })
        
        else:
            # Разбиваем на вкладки
            for city, city_points in grouped_data.items():
                if len(city_points) <= 2000:
                    # Весь город помещается на одну вкладку
                    df_city = pd.DataFrame(city_points)
                    column_order = ['ID точки', 'Имя точки', 'Тип точки', 'Город', 'Полигон', 'Аудитор', 'Широта', 'Долгота']
                    column_order = [col for col in column_order if col in df_city.columns]
                    df_city = df_city[column_order]
                    
                    # Формируем имя вкладки
                    sheet_name = city[:31]  # Ограничение Excel
                    
                    # Заменяем запрещенные символы
                    invalid_chars = ['/', '\\', '?', '*', ':', '[', ']']
                    for char in invalid_chars:
                        sheet_name = sheet_name.replace(char, '_')
                    
                    # Проверяем уникальность имени
                    original_name = sheet_name
                    counter = 1
                    while sheet_name in writer.sheets:
                        sheet_name = f"{original_name[:28]}_{counter}"
                        counter += 1
                    
                    df_city.to_excel(writer, sheet_name=sheet_name, index=False)
                    
                    sheet_info.append({
                        'Вкладка': sheet_name,
                        'Количество точек': len(df_city),
                        'Город': city,
                        'Полигон': 'Весь город',
                        'Аудиторов': df_city['Аудитор'].nunique()
                    })
                    
                    sheet_counter += 1
                else:
                    # Город нужно разбить по полигонам
                    city_points_df = pd.DataFrame(city_points)
                    
                    # Группируем по полигонам внутри города
                    for polygon in sorted(city_points_df['Полигон'].unique()):
                        polygon_points = city_points_df[city_points_df['Полигон'] == polygon].copy()
                        
                        if len(polygon_points) > 0:
                            # Готовим данные для полигона
                            column_order = ['ID точки', 'Имя точки', 'Тип точки', 'Город', 'Полигон', 'Аудитор', 'Широта', 'Долгота']
                            column_order = [col for col in column_order if col in polygon_points.columns]
                            polygon_points = polygon_points[column_order]
                            
                            # Формируем имя вкладки
                            if polygon != 'Не назначен':
                                sheet_name = f"{city[:15]}_{polygon[:15]}"
                            else:
                                sheet_name = f"{city[:20]}_Без полигона"
                            
                            # Очищаем имя вкладки
                            sheet_name = sheet_name[:31]
                            invalid_chars = ['/', '\\', '?', '*', ':', '[', ']']
                            for char in invalid_chars:
                                sheet_name = sheet_name.replace(char, '_')
                            
                            # Проверяем уникальность
                            original_name = sheet_name
                            counter = 1
                            while sheet_name in writer.sheets:
                                sheet_name = f"{original_name[:28]}_{counter}"
                                counter += 1
                            
                            polygon_points.to_excel(writer, sheet_name=sheet_name, index=False)
                            
                            sheet_info.append({
                                'Вкладка': sheet_name,
                                'Количество точек': len(polygon_points),
                                'Город': city,
                                'Полигон': polygon,
                                'Аудиторов': polygon_points['Аудитор'].nunique()
                            })
                            
                            sheet_counter += 1
        
        # 6. Добавляем сводную вкладку
        if sheet_info:
            df_summary = pd.DataFrame(sheet_info)
            df_summary = df_summary.sort_values('Количество точек', ascending=False)
            df_summary.to_excel(writer, sheet_name='Сводка', index=False)
        
        # 7. Добавляем итоговую статистику
        total_summary = pd.DataFrame([{
            'Всего точек': total_rows,
            'Количество вкладок': len(sheet_info),
            'Количество городов': len(grouped_data),
            'Дата выгрузки': datetime.now().strftime('%d.%m.%Y %H:%M'),
            'Статус': '✅ Успешно создано' if total_rows > 0 else '⚠️ Нет данных'
        }])
        total_summary.to_excel(writer, sheet_name='Итог', index=False)
    
    return excel_buffer.getvalue()

def create_kml_file(points_df, polygons):
    """Создает KML файл для Google Earth"""
    kml_header = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Полигоны и точки аудиторов</name>
'''
    
    kml_content = kml_header
    
    # Добавляем полигоны
    for poly_name, poly_info in polygons.items():
        if 'coordinates' in poly_info and len(poly_info['coordinates']) > 0:
            coords = poly_info['coordinates']
            coord_string = " ".join([f"{lon},{lat},0" for lat, lon in coords if len([lat, lon]) >= 2])
            
            if coord_string:
                kml_content += f'''
<Placemark>
<name>🗺️ {poly_name}</name>
<description>Аудитор: {poly_info.get('auditor', 'Неизвестно')}
Город: {poly_info.get('city', 'Неизвестно')}
Количество точек: {len(poly_info.get('points', []))}</description>
<styleUrl>#polygonStyle</styleUrl>
<Polygon>
<outerBoundaryIs>
<LinearRing>
<coordinates>{coord_string}</coordinates>
</LinearRing>
</outerBoundaryIs>
</Polygon>
</Placemark>
'''
    
    # Добавляем точки
    for _, point in points_df.iterrows():
        kml_content += f'''
<Placemark>
<name>🏪 {point['Название_Точки'][:30]}</name>
<description>ID: {point['ID_Точки']}
Тип: {point.get('Тип', 'Неизвестно')}
Адрес: {point.get('Адрес', 'Не указан')}</description>
<Point>
<coordinates>{point['Долгота']},{point['Широта']},0</coordinates>
</Point>
</Placemark>
'''
    
    kml_content += '''
<Style id="polygonStyle">
<LineStyle>
<color>ff0000ff</color>
<width>2</width>
</LineStyle>
<PolyStyle>
<color>400000ff</color>
<fill>1</fill>
<outline>1</outline>
</PolyStyle>
</Style>
</Document>
</kml>
'''
    
    return kml_content

def create_full_excel_report(points_df, auditors_df, city_stats_df, 
                            type_stats_df, summary_df, polygons):
    """Создает полный отчет Excel со всеми данными"""
    import io
    
    excel_buffer = io.BytesIO()
    
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        # Лист 1: Точки
        if points_df is not None:
            points_df.to_excel(writer, sheet_name='Точки', index=False)
        
        # Лист 2: Аудиторы
        if auditors_df is not None:
            auditors_df.to_excel(writer, sheet_name='Аудиторы', index=False)
        
        # Лист 3: Статистика по городам
        if city_stats_df is not None:
            city_stats_df.to_excel(writer, sheet_name='Статистика_городов', index=False)
        
        # Лист 4: План посещений
        if summary_df is not None:
            summary_df.to_excel(writer, sheet_name='План_посещений', index=False)
        
        # Лист 5: Полигоны
        if polygons:
            poly_data = []
            for poly_name, poly_info in polygons.items():
                poly_data.append({
                    'Полигон': poly_name,
                    'Аудитор': poly_info.get('auditor', 'Неизвестно'),
                    'Город': poly_info.get('city', 'Неизвестно'),
                    'Количество_точек': len(poly_info.get('points', [])),
                    'Координаты_полигона': str(poly_info.get('coordinates', []))
                })
            
            pd.DataFrame(poly_data).to_excel(writer, sheet_name='Полигоны', index=False)
    
    return excel_buffer.getvalue()

def calculate_polygon_center(poly_info):
    """Вычисляет центроид полигона"""
    try:
        # Из координат полигона
        if 'coordinates' in poly_info and poly_info['coordinates']:
            coords = poly_info['coordinates']
            lats = [c[0] for c in coords if len(c) >= 2]
            lons = [c[1] for c in coords if len(c) >= 2]
            
            if lats and lons:
                return sum(lats) / len(lats), sum(lons) / len(lons)
        
        # Из точек полигона
        if 'points' in poly_info and poly_info['points']:
            points = poly_info['points']
            lats = []
            lons = []
            
            for point in points:
                if len(point) >= 3:
                    lats.append(point[1])  # широта
                    lons.append(point[2])  # долгота
            
            if lats and lons:
                return sum(lats) / len(lats), sum(lons) / len(lons)
    except:
        pass
    
    return None, None

def create_light_map(points_df, polygons, max_points=200):
    """Создает легкую карту (ограниченное количество точек)"""
    import folium
    
    # Центр карты
    center_lat = points_df['Широта'].mean()
    center_lon = points_df['Долгота'].mean()
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
    
    # Ограничиваем количество точек для производительности
    if len(points_df) > max_points:
        display_points = points_df.sample(max_points)
        folium.Marker(
            location=[center_lat, center_lon],
            popup=f"Показано {max_points} из {len(points_df)} точек",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
    else:
        display_points = points_df
    
    # Простые маркеры для точек
    for _, point in display_points.iterrows():
        folium.CircleMarker(
            location=[point['Широта'], point['Долгота']],
            radius=3,
            popup=point['ID_Точки'],
            color='blue',
            fill=True
        ).add_to(m)
    
    # Полигоны
    for poly_name, poly_info in polygons.items():
        if 'coordinates' in poly_info and len(poly_info['coordinates']) > 2:
            folium.Polygon(
                locations=poly_info['coordinates'],
                popup=f"Полигон: {poly_name}",
                color='red',
                weight=2,
                fill=True,
                fill_opacity=0.1
            ).add_to(m)
    
    return m

# ==============================================
# РАЗДЕЛ ЗАГРУЗКИ ФАЙЛОВ
# ==============================================

st.header("📤 Загрузка файла")

upload_tab1, upload_tab2, upload_tab3 = st.tabs([
    "📁 Загрузка файла", 
    "📥 Скачать шаблон", 
    "📋 Описание полей"
])

with upload_tab1:
    st.subheader("Загрузите файл с данными")
    
    st.info("""
    **📝 Формат файла:** 
    - Один файл Excel с тремя вкладками: "Точки", "Аудиторы", "Факт_посещений"
    - Скачайте шаблон справа, заполните данные и загрузите обратно
    """)
    
    # Один загрузчик для всего файла
    data_file = st.file_uploader(
        "Файл с данными (Excel)", 
        type=['xlsx', 'xls'], 
        key="data_uploader_main",
        help="Excel файл с тремя вкладками: Точки, Аудиторы, Факт_посещений"
    )
    
    if data_file:
        st.success(f"✅ Загружен файл: {data_file.name}")
        
        # Сохраняем файл в session state
        st.session_state.data_file = data_file
        
        # Пробуем загрузить и проверить вкладки
        try:
            # Читаем названия всех листов
            xl = pd.ExcelFile(data_file)
            sheets = xl.sheet_names
            
            # Проверяем наличие необходимых листов
            required_sheets = ['Точки', 'Аудиторы', 'Факт_посещений']
            missing_sheets = [sheet for sheet in required_sheets if sheet not in sheets]
            
            if missing_sheets:
                st.warning(f"⚠️ В файле отсутствуют вкладки: {', '.join(missing_sheets)}")
                st.info("Убедитесь, что файл содержит вкладки с названиями: 'Точки', 'Аудиторы', 'Факт_посещений'")
            else:
                st.success("✅ Все необходимые вкладки найдены!")
                
                # Показываем предпросмотр каждой вкладки
                with st.expander("📋 Предпросмотр данных", expanded=False):
                    preview_tabs = st.tabs(["Точки", "Аудиторы", "Факт_посещений"])
                    
                    with preview_tabs[0]:
                        points_preview = pd.read_excel(data_file, sheet_name='Точки', nrows=5)
                        st.write(f"Точки: {len(points_preview)} строк")
                        st.dataframe(points_preview, use_container_width=True)
                    
                    with preview_tabs[1]:
                        auditors_preview = pd.read_excel(data_file, sheet_name='Аудиторы', nrows=5)
                        st.write(f"Аудиторы: {len(auditors_preview)} строк")
                        st.dataframe(auditors_preview, use_container_width=True)
                    
                    with preview_tabs[2]:
                        visits_preview = pd.read_excel(data_file, sheet_name='Факт_посещений', nrows=5)
                        st.write(f"Факт посещений: {len(visits_preview)} строк")
                        st.dataframe(visits_preview, use_container_width=True)
        
        except Exception as e:
            st.error(f"❌ Ошибка при чтении файла: {str(e)}")
    
    else:
        st.warning("⚠️ Загрузите файл с данными для продолжения")

with upload_tab2:
    st.subheader("Шаблон файла")
    
    st.info("""
    **📋 Инструкция:**
    1. Скачайте шаблон
    2. Заполните данные на каждой вкладке
    3. Сохраните файл
    4. Загрузите заполненный файл в приложение
    """)
    
    # Создаем файл с тремя вкладками
    excel_buffer = io.BytesIO()
    
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        # Вкладка 1: Точки
        points_template = create_template_points()
        points_template.to_excel(writer, sheet_name='Точки', index=False)
        
        # Вкладка 2: Аудиторы
        auditors_template = create_template_auditors()
        auditors_template.to_excel(writer, sheet_name='Аудиторы', index=False)
        
        # Вкладка 3: Факт_посещений
        visits_template = create_template_visits()
        visits_template.to_excel(writer, sheet_name='Факт_посещений', index=False)
    
    excel_data = excel_buffer.getvalue()
    
    # Кнопка скачивания
    st.download_button(
        label="📥 Скачать шаблон (Excel)",
        data=excel_data,
        file_name="шаблон_данных.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    # Предпросмотр вкладок шаблона
    st.markdown("---")
    st.markdown("**Предпросмотр шаблона:**")
    
    template_tabs = st.tabs(["Точки", "Аудиторы", "Факт_посещений"])
    
    with template_tabs[0]:
        st.markdown("##### Вкладка 'Точки'")
        st.dataframe(points_template, use_container_width=True)
        st.caption("Обязательные поля: ID_Точки, Широта, Долгота, Город, Тип")
    
    with template_tabs[1]:
        st.markdown("##### Вкладка 'Аудиторы'")
        st.dataframe(auditors_template, use_container_width=True)
        st.caption("Обязательные поля: ID_Сотрудника, Город")
    
    with template_tabs[2]:
        st.markdown("##### Вкладка 'Факт_посещений'")
        st.dataframe(visits_template, use_container_width=True)
        st.caption("Обязательные поля: ID_Точки, Дата_визита, ID_Сотрудника")
    
    st.markdown("---")
    st.success("✅ Шаблон содержит все три вкладки в одном файле Excel")

with upload_tab3:
    st.subheader("Описание полей")
    
    # Используем st.tabs для трех вкладок внутри описания
    desc_tabs = st.tabs(["Вкладка 'Точки'", "Вкладка 'Аудиторы'", "Вкладка 'Факт_посещений'"])
    
    with desc_tabs[0]:
        st.markdown("""
        ### Вкладка 'Точки'
        
        **Обязательные поля:**
        - `ID_Точки` - уникальный идентификатор
        - `Широта`, `Долгота` - координаты
        - `Тип` - Convenience/Hypermarket/Supermarket
        - `Город` - название города
        
        **Необязательные:**
        - `Адрес` - физический адрес
        - `Название_Точки` - название магазина
        - `Кол-во_посещений` - план посещений (по умолчанию 1)
        
        **Типы точек:**
        - `Convenience` → Мини
        - `Hypermarket` → Гипер
        - `Supermarket` → Супер
        """)
    
    with desc_tabs[1]:
        st.markdown("""
        ### Вкладка 'Аудиторы'
        
        **Обязательные поля:**
        - `ID_Сотрудника` - уникальный ID
        - `Город` - город работы
        """)
    
    with desc_tabs[2]:
        st.markdown("""
        ### Вкладка 'Факт_посещений'
        
        **Обязательные поля:**
        - `ID_Точки` - должен совпадать с ID во вкладке Точки
        - `Дата_визита` - дата посещения (дд.мм.гггг)
        - `ID_Сотрудника` - кто совершил визит
        
        **Формат:**
        - Одна строка = один визит
        - Можно оставить пустым, если данных нет
        """)

st.markdown("---")

# ==============================================
# КНОПКА РАСЧЕТА ПЛАНА
# ==============================================

# ТОЛЬКО ОДНА КНОПКА ВСЕМ КОДЕ!
calculate_button = st.button("🚀 Рассчитать план", type="primary", use_container_width=True, key="calculate_plan_btn")

if calculate_button:
    
    if 'data_file' not in st.session_state or st.session_state.data_file is None:
        st.error("⚠️ Пожалуйста, сначала загрузите файл с данными!")
        st.stop()
    
    data_file = st.session_state.data_file
    
    try:
        with st.spinner("🔄 Загрузка и обработка данных..."):
            # Загружаем данные из одного файла
            points_raw, auditors_raw, visits_raw = load_and_process_data(data_file)
            
            if points_raw is None or auditors_raw is None:
                st.stop()
            
            # Обрабатываем каждую таблицу
            points_df = load_and_process_points(points_raw)
            auditors_df = load_and_process_auditors(auditors_raw)
            visits_df = load_and_process_visits(visits_raw)
            
            if points_df is None or auditors_df is None:
                st.stop()
            
            # Сохраняем в session state
            st.session_state.points_df = points_df
            st.session_state.auditors_df = auditors_df
            st.session_state.visits_df = visits_df
            
            # Проверяем соответствие городов
            cities_points = set(points_df['Город'].unique())
            cities_auditors = set(auditors_df['Город'].unique())
            
            cities_without_auditors = cities_points - cities_auditors
            cities_without_points = cities_auditors - cities_points
            
            if cities_without_auditors:
                st.warning(f"⚠️ В городах {', '.join(cities_without_auditors)} нет аудиторов")
            
            if cities_without_points:
                st.warning(f"⚠️ Аудиторы в городах {', '.join(cities_without_points)} не имеют точек")
        
        # Показываем предпросмотр данных
        st.success("✅ Данные успешно загружены!")
        
        with st.expander("📋 Предпросмотр загруженных данных", expanded=False):
            tab1, tab2, tab3 = st.tabs(["Точки", "Аудиторы", "Факт посещений"])
            
            with tab1:
                st.write(f"Загружено точек: {len(points_df)}")
                st.dataframe(points_df.head(10), use_container_width=True)
            
            with tab2:
                st.write(f"Загружено аудиторов: {len(auditors_df)}")
                st.dataframe(auditors_df.head(10), use_container_width=True)
            
            with tab3:
                if not visits_df.empty:
                    st.write(f"Загружено записей о посещениях: {len(visits_df)}")
                    st.dataframe(visits_df.head(10), use_container_width=True)
                else:
                    st.info("Данные о посещениях отсутствуют")
        
        st.markdown("---")
        st.header("📅 Расчет плана визитов")
        
        with st.spinner("🔄 Распределение точек по аудиторам..."):
            # Распределяем точки по аудиторам
            points_assignment_df, polygons_info = distribute_points_to_auditors(points_df, auditors_df)
            
            # ИСПРАВЛЕНИЕ: проверяем оба возвращаемых значения
            if points_assignment_df is None or polygons_info is None:
                st.error("❌ Не удалось распределить точки по аудиторам")
                st.stop()
            
            # ✅ СОХРАНЯЕМ ДАННЫЕ ДЛЯ ВЫГРУЗКИ
            st.session_state.points_assignment_df = points_assignment_df  # ДЛЯ GOOGLE MAPS
            st.session_state.polygons_info = polygons_info  # ДЛЯ ПОЛИГОНОВ
            
            # Генерируем полигоны
            polygons = generate_polygons(polygons_info)
            st.session_state.polygons = polygons
            
            st.success(f"✅ Точки распределены по {len(polygons_info)} полигонам")
            st.success(f"✅ Сохранено {len(points_assignment_df)} назначений точек")
        
        with st.spinner("🔄 Распределение посещений по неделям..."):
            # Распределяем посещения по неделям
            detailed_plan_df = distribute_visits_by_weeks(
                points_assignment_df, points_df, year, quarter, coefficients
            )
            
            if detailed_plan_df.empty:
                st.error("❌ Не удалось распределить посещения по неделям")
                st.stop()
            
            st.success(f"✅ Распределено {len(detailed_plan_df)} записей по неделям")
        
        # Показываем краткую статистику распределения
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего точек", len(points_df))
        with col2:
            st.metric("Всего аудиторов", len(auditors_df))
        with col3:
            st.metric("Полигонов", len(polygons))
        with col4:
            total_visits = points_df['Кол-во_посещений'].sum()
            st.metric("Всего посещений", total_visits)
        
        # ==============================================
        # ПОЛНЫЙ РАСЧЕТ СО СТАТИСТИКОЙ
        # ==============================================
        
        with st.spinner("📊 Расчет полной статистики..."):
            try:
                # Рассчитываем полную статистику
                city_stats_df, type_stats_df, summary_df, detailed_with_fact = calculate_statistics(
                    points_df, visits_df, detailed_plan_df, year, quarter
                )
                
                # Сохраняем результаты в session state
                st.session_state.city_stats_df = city_stats_df
                st.session_state.type_stats_df = type_stats_df
                st.session_state.summary_df = summary_df
                st.session_state.details_df = detailed_with_fact
                st.session_state.plan_calculated = True  # ← ВОТ ТУТ, ВНУТРИ БЛОКА!
                
                st.success("✅ Полный расчет завершен! Статистика готова.")
                
                # Показываем итоговую статистику
                st.markdown("---")
                st.header("📊 Итоговая статистика")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Городов", len(city_stats_df))
                with col2:
                    total_plan = points_df['Кол-во_посещений'].sum()
                    st.metric("План посещений", total_plan)
                with col3:
                    total_fact = city_stats_df['Факт_посещений'].sum()
                    st.metric("Факт посещений", total_fact)
                with col4:
                    total_completion = round((total_fact / total_plan * 100) if total_plan > 0 else 0, 1)
                    st.metric("% выполнения", f"{total_completion}%")
                
                # Запускаем анимацию
                st.balloons()
                
            except Exception as e:
                st.error(f"❌ Ошибка при расчете статистики: {str(e)}")
                st.info("Будет показан частичный расчет без статистики")
                
                # Сохраняем хотя бы частичные результаты
                st.session_state.polygons_info = polygons_info
                st.session_state.points_assignment_df = points_assignment_df
                st.session_state.detailed_plan_df = detailed_plan_df
                st.session_state.plan_calculated = True  # ← И ЗДЕСЬ ТОЖЕ!
                
                st.success("✅ План частично рассчитан! Некоторые функции могут быть недоступны.")
    
    except Exception as e:
        st.error(f"❌ Произошла ошибка: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")

# ==============================================
# ИНФОРМАЦИЯ О ПРОГРЕССЕ
# ==============================================

if st.session_state.get('plan_partial', False):
    st.markdown("---")
    st.success("📊 **Этап 2/3 завершен:** План частично рассчитан")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("""
        **✅ Что сделано:**
        1. Данные загружены и обработаны
        2. Точки распределены по аудиторам
        3. Сгенерированы полигоны
        4. Посещения распределены по неделям
        """)
    
    with col2:
        st.info("""
        **⏭️ Следующие шаги (Часть 3):**
        1. Расчет полной статистики
        2. Создание сводных отчетов
        3. Визуализация данных
        4. Экспорт результатов
        """)
    
    # Показываем предпросмотр распределения
    if st.session_state.get('points_assignment_df') is not None:
        with st.expander("👥 Предпросмотр распределения точек по аудиторам", expanded=False):
            assignment_df = st.session_state.points_assignment_df
            summary = assignment_df.groupby(['Город', 'Аудитор', 'Полигон']).size().reset_index(name='Количество точек')
            st.dataframe(summary, use_container_width=True)

elif st.session_state.get('data_loaded', False):
    st.markdown("---")
    st.success("📊 **Этап 1/3 завершен:** Данные загружены и распределены по аудиторам")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("""
        **✅ Что сделано:**
        1. Файл загружен и проверен
        2. Данные обработаны
        3. Точки распределены по аудиторам
        4. Созданы полигоны для каждого аудитора
        """)
    
    with col2:
        st.info("""
        **⏭️ Следующие шаги (Часть 3):**
        1. Распределение посещений по неделям
        2. Генерация полигонов на карте
        3. Расчет статистики
        4. Создание отчетов
        """)

st.markdown("---")
st.caption("📋 **Часть 2/5:** Функции обработки данных, генерация полигонов, распределение посещений по неделям")

# ==============================================
# ВКЛАДКИ С РЕЗУЛЬТАТАМИ (ИСПРАВЛЕННЫЙ КОД)
# ==============================================

if st.session_state.plan_calculated:
    st.markdown("---")
    st.header("📊 Результаты расчета")
    
    # Проверка доступности folium
    try:
        import folium
        from streamlit_folium import folium_static
        FOLIUM_AVAILABLE = True
    except ImportError:
        FOLIUM_AVAILABLE = False
        st.warning("⚠️ Для отображения карты установите: pip install folium streamlit-folium")
    
    # 1. СОЗДАЕМ СПИСОК ВКЛАДОК
    available_tabs = []
    
    # Проверяем, какие данные есть
    if st.session_state.city_stats_df is not None:
        available_tabs.append("📊 Статистика по городам")
    
    if st.session_state.summary_df is not None:
        available_tabs.append("📋 План посещений")
    
    if (st.session_state.city_stats_df is not None or 
        st.session_state.type_stats_df is not None):
        available_tabs.append("📈 Диаграммы")
    
    available_tabs.append("📤 Выгрузка данных")
    
    # 2. СОЗДАЕМ ВКЛАДКИ ТОЛЬКО ОДИН РАЗ
    if available_tabs:
        results_tabs = st.tabs(available_tabs)
        
        # 3. РАБОТАЕМ С КАЖДОЙ ВКЛАДКОЙ ПО ПОРЯДКУ
        current_tab = 0
        
        # ВКЛАДКА 1: Статистика по городам
        if "📊 Статистика по городам" in available_tabs:
            with results_tabs[current_tab]:
                st.subheader("📊 Статистика по городам")
                
                if st.session_state.city_stats_df is not None:
                    city_stats = st.session_state.city_stats_df.copy()
                    
                    # Переименовываем колонки для отображения
                    display_cols = ['Город', 'Всего_точек', 'План_посещений', 'Факт_посещений', '%_выполнения']
                    display_df = city_stats[display_cols].copy()
                    display_df = display_df.rename(columns={
                        'Всего_точек': 'Всего точек',
                        'План_посещений': 'План посещений',
                        'Факт_посещений': 'Факт посещений',
                        '%_выполнения': '% выполнения'
                    })
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # Выгрузка в Excel
                    if not city_stats.empty:
                        try:
                            excel_buffer = io.BytesIO()
                            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                city_stats.to_excel(writer, sheet_name='Статистика_городов', index=False)
                            
                            excel_data = excel_buffer.getvalue()
                            b64 = base64.b64encode(excel_data).decode()
                            href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="статистика_городов.xlsx">📥 Скачать Excel</a>'
                            st.markdown(href, unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
                    else:
                        st.warning("Нет данных для выгрузки в Excel")
            current_tab += 1
        
        # ВКЛАДКА 2: План посещений 
        if "📋 План посещений" in available_tabs:
            with results_tabs[current_tab]:
                st.subheader("📋 План посещений")
                
                if st.session_state.summary_df is not None:
                    summary_df = st.session_state.summary_df.copy()
                    
                    if not summary_df.empty:
                        # Фильтры
                        st.markdown("### 🔍 Фильтры")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            # Фильтр по городам
                            all_cities = ["Все"] + sorted(summary_df['Город'].unique().tolist())
                            selected_city = st.selectbox("Город", all_cities, key="filter_city")
                        
                        with col2:
                            # Фильтр по аудиторам
                            all_auditors = ["Все"] + sorted(summary_df['Аудитор'].unique().tolist())
                            selected_auditor = st.selectbox("Аудитор", all_auditors, key="filter_auditor")
                        
                        with col3:
                            # Фильтр по неделям
                            all_weeks = ["Все"] + sorted(summary_df['ISO_Неделя'].unique().tolist())
                            selected_week = st.selectbox("Неделя", all_weeks, key="filter_week")
                        
                        with col4:
                            # Фильтр по полигонам
                            all_polygons = ["Все"] + sorted(summary_df['Полигон'].unique().tolist())
                            selected_polygon = st.selectbox("Полигон", all_polygons, key="filter_polygon")
                        
                        # Применяем фильтры
                        filtered_df = summary_df.copy()
                        
                        if selected_city != "Все":
                            filtered_df = filtered_df[filtered_df['Город'] == selected_city]
                        
                        if selected_auditor != "Все":
                            filtered_df = filtered_df[filtered_df['Аудитор'] == selected_auditor]
                        
                        if selected_week != "Все":
                            filtered_df = filtered_df[filtered_df['ISO_Неделя'] == selected_week]
                        
                        if selected_polygon != "Все":
                            filtered_df = filtered_df[filtered_df['Полигон'] == selected_polygon]
                        
                        # Показываем статистику фильтра
                        st.markdown(f"**📊 Найдено записей:** {len(filtered_df)}")
                        
                        if len(filtered_df) > 0:
                            # Суммарная статистика
                            total_plan = filtered_df['План_посещений'].sum()
                            total_fact = filtered_df['Факт_посещений'].sum() if 'Факт_посещений' in filtered_df.columns else 0
                            completion = round((total_fact / total_plan * 100) if total_plan > 0 else 0, 1)
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("План посещений", total_plan)
                            with col2:
                                st.metric("Факт посещений", total_fact)
                            with col3:
                                st.metric("% выполнения", f"{completion}%")
                            
                            st.markdown("---")
                            
                            # Подготовка данных для отображения
                            display_df = filtered_df.copy()
                            
                            # Форматируем даты
                            display_df['Дата_начала'] = pd.to_datetime(display_df['Дата_начала']).dt.strftime('%d.%m.%Y')
                            display_df['Дата_окончания'] = pd.to_datetime(display_df['Дата_окончания']).dt.strftime('%d.%m.%Y')
                            
                            # Переименовываем колонки для читаемости
                            display_df = display_df.rename(columns={
                                'ISO_Неделя': 'Неделя',
                                'Дата_начала': 'Начало недели',
                                'Дата_окончания': 'Конец недели',
                                'План_посещений': 'План',
                                'Факт_посещений': 'Факт',
                                '%_выполнения': '% выполнения'
                            })
                            
                            # Выбираем колонки для отображения
                            display_columns = ['Город', 'Полигон', 'Аудитор', 'Неделя', 
                                             'Начало недели', 'Конец недели', 'План', 'Факт', '% выполнения']
                            
                            # Оставляем только существующие колонки
                            display_columns = [col for col in display_columns if col in display_df.columns]
                            
                            st.dataframe(
                                display_df[display_columns], 
                                use_container_width=True, 
                                height=400,
                                hide_index=True
                            )
                            
                            # Выгрузка в Excel
                            st.markdown("---")
                            st.subheader("💾 Выгрузка данных")
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                # Выгрузка отфильтрованных данных
                                try:
                                    excel_buffer = io.BytesIO()
                                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                        filtered_df.to_excel(writer, sheet_name='План_посещений', index=False)
                                    
                                    excel_data = excel_buffer.getvalue()
                                    st.download_button(
                                        label="📥 Скачать Excel (фильтр)",
                                        data=excel_data,
                                        file_name=f"план_посещений_{year}_Q{quarter}_фильтр.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True
                                    )
                                except Exception as e:
                                    st.error(f"❌ Ошибка: {str(e)}")
                            
                            with col2:
                                # Выгрузка всех данных
                                try:
                                    excel_buffer = io.BytesIO()
                                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                        summary_df.to_excel(writer, sheet_name='План_посещений', index=False)
                                    
                                    excel_data = excel_buffer.getvalue()
                                    st.download_button(
                                        label="📥 Скачать Excel (все данные)",
                                        data=excel_data,
                                        file_name=f"план_посещений_{year}_Q{quarter}_все.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True
                                    )
                                except Exception as e:
                                    st.error(f"❌ Ошибка: {str(e)}")
                        else:
                            st.info("Нет данных по выбранным фильтрам")
                    else:
                        st.info("Нет данных для отображения")
            current_tab += 1
        
        # ВКЛАДКА 3: Диаграммы
        if "📈 Диаграммы" in available_tabs:
            with results_tabs[current_tab]:
                st.subheader("📈 Диаграммы и статистика")
                
                # 1. Диаграмма выполнения плана по городам
                if st.session_state.city_stats_df is not None:
                    city_stats = st.session_state.city_stats_df.copy()
                    
                    # Проверяем, есть ли нужные колонки
                    if 'Город' in city_stats.columns and '%_выполнения' in city_stats.columns:
                        # Создаем график
                        fig = px.bar(city_stats, 
                                    x='Город', 
                                    y='%_выполнения',
                                    title='% выполнения плана по городам',
                                    color='%_выполнения',
                                    color_continuous_scale='RdYlGn')
                        
                        fig.update_layout(height=400)
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Выгрузка статистики по городам в Excel
                        if not city_stats.empty:
                            try:
                                excel_buffer = io.BytesIO()
                                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                    city_stats.to_excel(writer, sheet_name='Статистика_городов', index=False)
                                
                                excel_data = excel_buffer.getvalue()
                                b64 = base64.b64encode(excel_data).decode()
                                href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="статистика_городов.xlsx">📥 Скачать статистику по городам</a>'
                                st.markdown(href, unsafe_allow_html=True)
                            except Exception as e:
                                st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
                    else:
                        st.warning("Недостаточно данных для построения диаграммы по городам")
                
                # 2. Статистика по типам точек
                if st.session_state.type_stats_df is not None:
                    st.markdown("### 🏪 Статистика по типам точек")
                    type_stats = st.session_state.type_stats_df.copy()
                    
                    # Отображаем таблицу
                    if not type_stats.empty:
                        st.dataframe(type_stats, use_container_width=True, hide_index=True)
                        
                        # Простая диаграмма по типам точек
                        if 'Тип' in type_stats.columns and 'План_посещений' in type_stats.columns:
                            fig2 = px.bar(type_stats,
                                         x='Тип',
                                         y='План_посещений',
                                         title='План посещений по типам точек',
                                         color='Тип')
                            fig2.update_layout(height=300, showlegend=False)
                            st.plotly_chart(fig2, use_container_width=True)
                        
                        # Выгрузка статистики по типам в Excel
                        try:
                            excel_buffer = io.BytesIO()
                            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                type_stats.to_excel(writer, sheet_name='Статистика_типов', index=False)
                            
                            excel_data = excel_buffer.getvalue()
                            b64 = base64.b64encode(excel_data).decode()
                            href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="статистика_типов_точек.xlsx">📥 Скачать статистику по типам точек</a>'
                            st.markdown(href, unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
                
                # 3. Общая статистика
                st.markdown("### 📊 Общая статистика")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.session_state.points_df is not None:
                        total_points = len(st.session_state.points_df)
                        st.metric("Всего точек", total_points)
                
                with col2:
                    if st.session_state.auditors_df is not None:
                        total_auditors = len(st.session_state.auditors_df)
                        st.metric("Всего аудиторов", total_auditors)
                
                with col3:
                    if st.session_state.polygons is not None:
                        total_polygons = len(st.session_state.polygons)
                        st.metric("Полигонов", total_polygons)
            current_tab += 1
        
            # ВКЛАДКА 4: Выгрузка данных
            if available_tabs and "📤 Выгрузка данных" in available_tabs:
                with results_tabs[current_tab]:
                    st.subheader("📤 Выгрузка данных для карт и отчетов")
                    
                    st.info("""
                    **Выберите формат выгрузки:**  
                    🔹 **Excel для Google Карт** - данные с координатами для импорта  
                    🔹 **KML для Google Earth** - географические данные с полигонами  
                    🔹 **Полный отчет Excel** - все данные для анализа  
                    """)
                    
                    st.markdown("---")
                    
                    # КОЛОНКА 1: Excel для Google Карт
                    with st.container(border=True):
                        st.markdown("### 📊 Excel для Google Карт")
                        st.caption("Формат для импорта в Google Карты / My Maps")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.markdown("""
                            **Что включено:**
                            - Все точки с координатами
                            - Полигоны с центроидами
                            - Описания и метаданные
                            - Готовые столбцы для импорта
                            """)
                        
                        with col2:
                            if st.button("📥 Скачать Excel", key="download_excel_google", use_container_width=True):
                                with st.spinner("🔄 Создание Excel файла для Google Карт..."):
                                    try:
                                        if 'polygons' not in st.session_state or not st.session_state.polygons:
                                            st.error("❌ Нет данных полигонов")
                                        else:
                                            excel_buffer = create_google_maps_excel(
                                                st.session_state.points_df,
                                                st.session_state.polygons,
                                                st.session_state.get('points_assignment_df')  # Передаем assignment_df
                                            )
                                            
                                            # Сразу показываем кнопку скачивания
                                            st.download_button(
                                                label="📊 Нажмите, чтобы скачать Excel для Google Карт",
                                                data=excel_buffer,
                                                file_name=f"google_maps_export_{year}_Q{quarter}.xlsx",
                                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                use_container_width=True,
                                                key=f"google_excel_{year}_{quarter}_{datetime.now().timestamp()}"
                                            )
                                            st.success("✅ Excel файл создан! Нажмите кнопку выше для скачивания")
                                    except Exception as e:
                                        st.error(f"❌ Ошибка создания Excel: {str(e)}")
                    
                    # КОЛОНКА 2: KML для Google Earth
                    with st.container(border=True):
                        st.markdown("### 🗺️ KML для Google Earth")
                        st.caption("Географический формат для GIS-систем")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.markdown("""
                            **Что включено:**
                            - Полигоны как замкнутые контуры
                            - Точки с метками
                            - Иерархия по городам/аудиторам
                            - Поддерживается в Google Earth, QGIS
                            """)
                        
                        with col2:
                            if st.button("📥 Скачать KML", key="download_kml", use_container_width=True):
                                with st.spinner("🔄 Создание KML файла для Google Earth..."):
                                    try:
                                        if 'polygons' not in st.session_state or not st.session_state.polygons:
                                            st.error("❌ Нет данных полигонов")
                                        else:
                                            kml_content = create_kml_file(
                                                st.session_state.points_df,
                                                st.session_state.polygons
                                            )
                                            
                                            # Сразу показываем кнопку скачивания
                                            st.download_button(
                                                label="🗺️ Нажмите, чтобы скачать KML для Google Earth",
                                                data=kml_content.encode('utf-8'),
                                                file_name=f"polygons_{year}_Q{quarter}.kml",
                                                mime="application/vnd.google-earth.kml+xml",
                                                use_container_width=True,
                                                key=f"kml_{year}_{quarter}_{datetime.now().timestamp()}"
                                            )
                                            st.success("✅ KML файл создан! Нажмите кнопку выше для скачивания")
                                    except Exception as e:
                                        st.error(f"❌ Ошибка создания KML: {str(e)}")
                    
                    # КОЛОНКА 3: Полный отчет Excel
                    with st.container(border=True):
                        st.markdown("### 📋 Полный отчет Excel")
                        st.caption("Все данные приложения в одном файле")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.markdown("""
                            **Что включено:**
                            - Статистика по городам
                            - План посещений по неделям
                            - Распределение по аудиторам
                            - Данные по точкам
                            - Полигоны и координаты
                            """)
                        
                        with col2:
                            if st.button("📥 Скачать полный отчет", key="download_full_report", use_container_width=True):
                                with st.spinner("🔄 Создание полного отчета Excel..."):
                                    try:
                                        full_excel = create_full_excel_report(
                                            st.session_state.points_df,
                                            st.session_state.auditors_df,
                                            st.session_state.city_stats_df,
                                            st.session_state.type_stats_df,
                                            st.session_state.summary_df,
                                            st.session_state.polygons
                                        )
                                        
                                        # Сразу показываем кнопку скачивания
                                        st.download_button(
                                            label="📋 Нажмите, чтобы скачать полный отчет Excel",
                                            data=full_excel,
                                            file_name=f"full_report_{year}_Q{quarter}.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            use_container_width=True,
                                            key=f"full_report_{year}_{quarter}_{datetime.now().timestamp()}"
                                        )
                                        st.success("✅ Полный отчет создан! Нажмите кнопку выше для скачивания")
                                    except Exception as e:
                                        st.error(f"❌ Ошибка создания отчета: {str(e)}")
                            
                            
        # === ИНСТРУКЦИИ ===
        st.markdown("---")
        with st.expander("📋 Инструкции по импорту", expanded=False):
            tab1, tab2, tab3 = st.tabs(["Google Карты", "Google Earth", "Excel"])
            
            with tab1:
                st.markdown("""
                **Импорт в Google Карты:**
                1. Откройте [Google My Maps](https://www.google.com/maps/d/)
                2. Создайте новую карту → "Импорт"
                3. Выберите скачанный Excel файл
                4. Укажите столбцы:
                   - **Широта** → Latitude
                   - **Долгота** → Longitude  
                   - **Название** → Name
                   - **Описание** → Description
                5. Нажмите "Импортировать"
                """)
            
            with tab2:
                st.markdown("""
                **Импорт в Google Earth:**
                1. Откройте Google Earth Pro
                2. Файл → Открыть
                3. Выберите KML файл
                4. Данные появятся в панели "Мои места"
                5. Щелкните по объектам для просмотра информации
                """)
            
            with tab3:
                st.markdown("""
                **Использование Excel отчета:**
                - **Лист 1:** Точки с координатами
                - **Лист 2:** Статистика по городам
                - **Лист 3:** План посещений
                - **Лист 4:** Полигоны и аудиторы
                - **Лист 5:** Сводная таблица
                """)
        
        # === АЛЬТЕРНАТИВА КАРТЕ ===
        st.markdown("---")
        with st.expander("📍 Быстрый просмотр данных (без карты)", expanded=False):
            if st.session_state.polygons:
                # Показываем таблицу с полигонами
                poly_data = []
                for poly_name, poly_info in st.session_state.polygons.items():
                    poly_data.append({
                        'Полигон': poly_name,
                        'Аудитор': poly_info.get('auditor', 'Неизвестно'),
                        'Город': poly_info.get('city', 'Неизвестно'),
                        'Точек': len(poly_info.get('points', [])),
                        'Центроид': f"{poly_info.get('center_lat', 'N/A'):.4f}, {poly_info.get('center_lon', 'N/A'):.4f}" 
                        if 'center_lat' in poly_info else "N/A"
                    })
                
                if poly_data:
                    df_poly = pd.DataFrame(poly_data)
                    st.dataframe(df_poly, use_container_width=True, hide_index=True)
                    
                    # Кнопка для скачивания этой таблицы
                    csv = df_poly.to_csv(index=False, sep=';').encode('utf-8')
                    st.download_button(
                        label="📋 Скачать список полигонов (CSV)",
                        data=csv,
                        file_name=f"polygons_list_{year}_Q{quarter}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            else:
                st.info("Нет данных о полигонах")
        
        # Информация о данных
        st.markdown("---")
        st.caption(f"📊 Данные: {len(st.session_state.points_df) if st.session_state.points_df is not None else 0} точек, "
                  f"{len(st.session_state.polygons) if st.session_state.polygons else 0} полигонов, "
                  f"{len(st.session_state.auditors_df) if st.session_state.auditors_df is not None else 0} аудиторов")
    current_tab += 1





