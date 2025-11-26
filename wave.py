"""
DETECTOR DE COR SIMPLES COM RASTREAMENTO
Clique em um objeto na câmera para capturar sua cor
O programa vai criar um filtro e rastrear o objeto mesmo quando ele sair da câmera
"""

import cv2
import numpy as np
import ctypes
import time

# Prefer using pyautogui when available (higher-level, often less blocked).
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    _use_pyautogui = True
except Exception:
    _use_pyautogui = False

# Prefer keyboard for press-and-hold if available
try:
    import keyboard
    _use_keyboard = True
except Exception:
    _use_keyboard = False

# Variáveis globais
hsv_color = None
frame_hsv = None
last_position = None  # Armazena última posição conhecida
search_radius = 100   # Raio de busca em pixels

# Virtual mouse globals
virtual_mouse_enabled = False  # Ativa movimento do mouse quando True
window_minimized = False       # Janela escondida/fora da tela
prev_mouse_pos = None          # Para suavizar movimento
last_area = 0                  # Última área detectada do objeto
area_threshold = 80            # Mínimo de área para mover o mouse (ajustável)

# Estado de teclas globais para suportar ações quando a janela perde foco
prev_key_states = {'esc': False, '0': False, 'r': False}
last_key_action_time = 0.0
KEY_DEBOUNCE = 0.25  # segundos para debouncing de ações globais

# Helpers to restore the OpenCV window using Win32 APIs
def _restore_window_by_title(title='Detector de Cor'):
    try:
        hwnd = ctypes.windll.user32.FindWindowA(None, title.encode('utf-8'))
        if hwnd:
            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            # Move to a visible position and bring to foreground
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 100, 100, 0, 0, 0x0001)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

# Windows screen size (assume Windows)
screen_w = ctypes.windll.user32.GetSystemMetrics(0)
screen_h = ctypes.windll.user32.GetSystemMetrics(1)

def mouse_click(event, x, y, flags, param):
    """Captura a cor quando você clica na câmera"""
    global hsv_color, frame_hsv
    
    if event == cv2.EVENT_LBUTTONDOWN and frame_hsv is not None:
        # Pega o valor HSV do pixel clicado (converter para int para evitar underflow/overflow)
        h_val, s_val, v_val = map(int, frame_hsv[y, x])

        # Criar range de tolerância (usar ints, depois converter para uint8)
        h_lower = max(0, h_val - 10)
        h_upper = min(180, h_val + 10)
        s_lower = max(0, s_val - 40)
        s_upper = min(255, s_val + 40)
        v_lower = max(0, v_val - 40)
        v_upper = min(255, v_val + 40)

        # Garantir que os arrays de limite sejam do mesmo tipo (uint8) esperado pelo OpenCV
        hsv_color = (
            np.array([h_lower, s_lower, v_lower], dtype=np.uint8),
            np.array([h_upper, s_upper, v_upper], dtype=np.uint8)
        )
        
        print(f"\n{'='*50}")
        print(f"✓ COR CAPTURADA EM ({x}, {y})!")
        print(f"{'='*50}")
        print(f"Cor referência: H={h_val}  S={s_val}  V={v_val}")
        print(f"Range: H({h_lower}-{h_upper}) S({s_lower}-{s_upper}) V({v_lower}-{v_upper})")
        print(f"{'='*50}\n")

def find_object_near_position(mask, last_pos, search_rad):
    """
    Procura pelo objeto perto da última posição conhecida
    Retorna a posição encontrada ou None
    """
    if last_pos is None:
        return None
    
    cx_last, cy_last = last_pos
    h, w = mask.shape
    
    # Criar ROI (Region of Interest) ao redor da última posição
    x_start = max(0, cx_last - search_rad)
    x_end = min(w, cx_last + search_rad)
    y_start = max(0, cy_last - search_rad)
    y_end = min(h, cy_last + search_rad)
    
    # Extrair ROI
    roi = mask[y_start:y_end, x_start:x_end]
    
    # Procurar contornos no ROI
    contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Encontrar o maior contorno
        maior_contorno = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(maior_contorno)
        
        if area > 100:  # Mínimo de pixels
            x, y, w_box, h_box = cv2.boundingRect(maior_contorno)
            # Converter coordenadas de volta para o frame inteiro
            cx = x_start + x + w_box // 2
            cy = y_start + y + h_box // 2
            return (cx, cy), (x_start + x, y_start + y, w_box, h_box), area
    
    return None, None, None


def find_similar_object_fast(frame_hsv, hsv_ref, last_pos, search_rad, tolerance_increase=0):
    """
    Busca por objetos SIMILARES ao referência em tempo real
    MUITO RÁPIDA - aumenta tolerância progressivamente até encontrar
    Começa restrita (cor semelhante) e vai abrindo conforme o tempo passa
    """
    if last_pos is None:
        return None, None, None
    
    # Converter referências para int para evitar operações em uint8 que causam wrap-around
    h_ref, s_ref, v_ref = map(int, hsv_ref)

    # Tolerância cresce AGRESSIVAMENTE para encontrar similares rápido
    # Multiplicadores maiores = tolerância abre MUITO mais rápido
    h_tol = 12 + (tolerance_increase * 0.6)       # Hue: sensível ao inicio, abre depois
    s_tol = 45 + (tolerance_increase * 2.0)       # Saturação: abre AGRESSIVO
    v_tol = 45 + (tolerance_increase * 2.0)       # Value: abre AGRESSIVO

    h_lower = int(max(0, h_ref - int(h_tol)))
    h_upper = int(min(180, h_ref + int(h_tol)))
    s_lower = int(max(0, s_ref - int(s_tol)))
    s_upper = int(min(255, s_ref + int(s_tol)))
    v_lower = int(max(0, v_ref - int(v_tol)))
    v_upper = int(min(255, v_ref + int(v_tol)))

    # Garantir mesmo dtype (uint8) para lower/upper - requerido por cv2.inRange
    lower = np.array([h_lower, s_lower, v_lower], dtype=np.uint8)
    upper = np.array([h_upper, s_upper, v_upper], dtype=np.uint8)
    
    # Criar máscara com tolerância aumentada
    mask = cv2.inRange(frame_hsv, lower, upper)
    
    # Limpeza otimizada (pequena = rápida)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    # Procurar próximo à última posição
    cx_last, cy_last = last_pos
    frame_h, frame_w = frame_hsv.shape[:2]
    
    x_start = max(0, cx_last - search_rad)
    x_end = min(frame_w, cx_last + search_rad)
    y_start = max(0, cy_last - search_rad)
    y_end = min(frame_h, cy_last + search_rad)
    
    roi = mask[y_start:y_end, x_start:x_end]
    contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Encontrar MAIOR contorno no ROI
        maior_contorno = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(maior_contorno)
        
        if area > 70:  # Limiar MUITO menor para pegar similares pequenos
            x, y, w_box, h_box = cv2.boundingRect(maior_contorno)
            cx = x_start + x + w_box // 2
            cy = y_start + y + h_box // 2
            return (cx, cy), (x_start + x, y_start + y, w_box, h_box), area
    
    return None, None, None


def _move_mouse_to_screen(cx, cy, frame_w, frame_h, smooth=0.25):
    """Mapeia coordenadas do frame para a tela e move o cursor (suaviza por filter exponencial)."""
    global prev_mouse_pos, screen_w, screen_h

    # Calcular posição relativa na tela
    tx = int(cx / float(frame_w) * screen_w)
    ty = int(cy / float(frame_h) * screen_h)

    if prev_mouse_pos is None:
        prev_mouse_pos = (tx, ty)

    # Suavizar movimento
    mx = int(prev_mouse_pos[0] * (1.0 - smooth) + tx * smooth)
    my = int(prev_mouse_pos[1] * (1.0 - smooth) + ty * smooth)

    # Mover cursor (pyautogui se disponível, senão ctypes)
    if _use_pyautogui:
        try:
            pyautogui.moveTo(mx, my, duration=0)
        except Exception:
            ctypes.windll.user32.SetCursorPos(mx, my)
    else:
        ctypes.windll.user32.SetCursorPos(mx, my)

    prev_mouse_pos = (mx, my)


def _mouse_click(button='left'):
    """Gera evento de clique do mouse (left/right) no Windows."""
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010

    if _use_pyautogui:
        try:
            if button == 'left':
                pyautogui.click(button='left')
            else:
                pyautogui.click(button='right')
            return
        except Exception:
            pass

    # Fallback para ctypes se pyautogui não estiver disponível ou falhar
    if button == 'left':
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    else:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def _mouse_down(button='left'):
    """Pressiona o botão do mouse (não solta)."""
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    if _use_pyautogui:
        try:
            pyautogui.mouseDown(button=button)
            return
        except Exception:
            pass
    if button == 'left':
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    else:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)


def _mouse_up(button='left'):
    """Solta o botão do mouse."""
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTUP = 0x0010
    if _use_pyautogui:
        try:
            pyautogui.mouseUp(button=button)
            return
        except Exception:
            pass
    if button == 'left':
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    else:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def main():
    global hsv_color, frame_hsv, last_position, search_radius
    global virtual_mouse_enabled, window_minimized, prev_mouse_pos, last_area
    global prev_key_states, last_key_action_time
    
    print("\n" + "="*60)
    print("  DETECTOR DE COR COM RASTREAMENTO INTELIGENTE")
    print("  + Busca por Cores Similares (NOVO!)")
    print("="*60)
    print("\nCOMO USAR:")
    print("1. A câmera vai abrir")
    print("2. CLIQUE no objeto que você quer detectar")
    print("3. O programa vai rastrear o objeto!")
    print("4. Se sair da câmera, procurará por CORES SIMILARES!")
    print("5. Pressione 'R' para resetar ou 'ESC' para sair")
    print("\nFASES:")
    print("  Verde    = Objeto encontrado (cor exata)")
    print("  Amarelo  = Rastreando objeto exato")
    print("  Azul     = Rastreando cor SIMILAR")
    print("  Vermelho = Procurando (sem deteccao)")
    print("="*60 + "\n")
    
    # Iniciar câmera
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("✗ Erro: Câmera não encontrada!")
        return
    
    # Configurar câmera - otimizado para velocidade
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    
    # Criar janela e configurar clique do mouse
    cv2.namedWindow('Detector de Cor')
    cv2.setMouseCallback('Detector de Cor', mouse_click)
    
    print("✓ Câmera aberta. Clique no objeto que deseja detectar...")
    print("  Sistema agora procura por cores similares!\n")
    
    frames_sem_deteccao = 0  # Contador para aumentar raio de busca
    tolerance_bonus = 0      # Aumenta tolerância para similares
    
    tick_freq = cv2.getTickFrequency()
    
    while True:
        inicio_frame = cv2.getTickCount()
        ret, frame = cap.read()
        if not ret:
            print("✗ Erro ao capturar frame!")
            break
        
        # Espelhar frame
        frame = cv2.flip(frame, 1)
        
        # Converter para HSV
        frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        frame_resultado = frame.copy()
        
        # Se cor foi capturada
        if hsv_color is not None:
            lower, upper = hsv_color
            
            # Calcular cor referência (centro do range)
            hsv_ref = np.array([
                (int(lower[0]) + int(upper[0])) // 2,
                (int(lower[1]) + int(upper[1])) // 2,
                (int(lower[2]) + int(upper[2])) // 2
            ])
            
            # Criar máscara com cor exata
            mask = cv2.inRange(frame_hsv, lower, upper)
            
            # Limpeza otimizada
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # Procurar contornos
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            objeto_encontrado = False
            
            if contours:
                maior_contorno = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(maior_contorno)
                
                if area > 100:
                    objeto_encontrado = True
                    frames_sem_deteccao = 0
                    tolerance_bonus = 0
                    
                    x, y, w, h_bbox = cv2.boundingRect(maior_contorno)
                    cx = x + w // 2
                    cy = y + h_bbox // 2
                    last_position = (cx, cy)
                    last_area = area
                    
                    cv2.rectangle(frame_resultado, (x, y), (x + w, y + h_bbox), (0, 255, 0), 3)
                    cv2.circle(frame_resultado, (cx, cy), 8, (0, 255, 0), -1)
                    cv2.putText(frame_resultado, f'DETECTADO - Area: {int(area)} px', (x, y - 15),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Se não encontrou, usar rastreamento inteligente
            if not objeto_encontrado and last_position is not None:
                frames_sem_deteccao += 1
                
                # Aumentar tolerância RAPIDAMENTE a cada 5 frames
                if frames_sem_deteccao % 5 == 0 and frames_sem_deteccao > 3:
                    tolerance_bonus = min(120, tolerance_bonus + 10)
                
                raio_aumentado = search_radius + (frames_sem_deteccao * 10)
                
                # TENTATIVA 1: Procurar objeto EXATO
                pos, bbox, area = find_object_near_position(mask, last_position, raio_aumentado)
                
                if pos is not None:
                    cx, cy = pos
                    x, y, w, h_bbox = bbox
                    last_position = (cx, cy)
                    frames_sem_deteccao = 0
                    last_area = area
                    
                    cv2.rectangle(frame_resultado, (x, y), (x + w, y + h_bbox), (0, 255, 255), 3)
                    cv2.circle(frame_resultado, (cx, cy), 8, (0, 255, 255), -1)
                    cv2.circle(frame_resultado, last_position, raio_aumentado, (0, 255, 255), 2)
                    cv2.putText(frame_resultado, f'RASTREANDO (Exato)', (x, y - 15),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                else:
                    # TENTATIVA 2: Procurar cores SIMILARES
                    pos_sim, bbox_sim, area_sim = find_similar_object_fast(
                        frame_hsv, hsv_ref, last_position, raio_aumentado, tolerance_bonus
                    )
                    
                    if pos_sim is not None:
                        cx, cy = pos_sim
                        x, y, w, h_bbox = bbox_sim
                        last_position = (cx, cy)
                        frames_sem_deteccao = 0
                        last_area = area_sim
                        
                        cv2.rectangle(frame_resultado, (x, y), (x + w, y + h_bbox), (255, 140, 0), 3)
                        cv2.circle(frame_resultado, (cx, cy), 8, (255, 140, 0), -1)
                        cv2.circle(frame_resultado, last_position, raio_aumentado, (255, 140, 0), 2)
                        cv2.putText(frame_resultado, f'RASTREANDO (Similar)', (x, y - 15),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 140, 0), 2)
                        cv2.putText(frame_resultado, f'Tolerancia: +{tolerance_bonus}', (x, y + h_bbox + 20),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 140, 0), 1)
                    else:
                        # FASE 3: PROCURANDO
                        if frames_sem_deteccao > 60:
                            cv2.putText(frame_resultado, 'OBJETO PERDIDO!', (50, 100),
                                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
                            cv2.putText(frame_resultado, 'Clique novamente para capturar', (50, 140),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 1)
                            last_position = None
                            frames_sem_deteccao = 0
                            tolerance_bonus = 0
                        else:
                            cx, cy = last_position
                            cv2.circle(frame_resultado, (cx, cy), raio_aumentado, (0, 0, 255), 2)
                            cv2.circle(frame_resultado, (cx, cy), 10, (0, 0, 255), 2)
                            cv2.putText(frame_resultado, f'PROCURANDO ({frames_sem_deteccao}/60)', (50, 50),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                            cv2.putText(frame_resultado, f'Tol: +{tolerance_bonus}  Raio: {raio_aumentado}px', (50, 80),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
            
            # Info HSV
            info_text = f"H:{int(lower[0])}-{int(upper[0])} S:{int(lower[1])}-{int(upper[1])} V:{int(lower[2])}-{int(upper[2])}"
            cv2.putText(frame_resultado, info_text, (15, frame_resultado.shape[0] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        else:
            cv2.putText(frame_resultado, 'CLIQUE no objeto para capturar sua cor', (30, 80),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 165, 255), 2)
            cv2.putText(frame_resultado, 'Sistema procurara por cores similares!', (30, 120),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 200, 0), 2)
        
        # Legenda
        cv2.putText(frame_resultado, 'R: Reset | ESC: Sair', (15, frame_resultado.shape[0] - 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(frame_resultado, 'Verde=Detectado | Amarelo=Exato | Azul=Similar | Vermelho=Procurando',
                   (15, frame_resultado.shape[0] - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        
        # Mostrar frame
        cv2.imshow('Detector de Cor', frame_resultado)

        # Se o modo mouse virtual estiver ativo, mover o cursor para a última posição
        # Somente mover se a última área detectada for maior que o limiar
        if virtual_mouse_enabled and last_position is not None and last_area >= area_threshold:
            fh, fw = frame.shape[0], frame.shape[1]
            _move_mouse_to_screen(last_position[0], last_position[1], fw, fh)

        # Controles
        key = cv2.waitKey(1) & 0xFF
        # Handle key events (single-click triggers)
        if key == 27:
            break
        elif key == ord('r') or key == ord('R'):
            hsv_color = None
            last_position = None
            frames_sem_deteccao = 0
            tolerance_bonus = 0
            print("\n✓ Reset! Clique em um objeto para começar...\n")
        elif key == ord('a'):
            # Clique esquerdo (curto)
            _mouse_click('left')
            print('→ Clique esquerdo (a) enviado')
        elif key == ord('l'):
            # Clique direito (curto)
            _mouse_click('right')
            print('→ Clique direito (l) enviado')
        elif key == ord('0'):
            # Toggle modo virtual / minimizado
            window_minimized = not window_minimized
            virtual_mouse_enabled = window_minimized
            if window_minimized:
                # mover janela para fora da tela (simular minimizado)
                try:
                    cv2.moveWindow('Detector de Cor', -2000, -2000)
                except Exception:
                    pass
                print('→ MODO MOUSE VIRTUAL ATIVADO (janela escondida). Teclas: a=left, l=right, 0=restaurar')
            else:
                # Restaurar janela de forma mais robusta usando Win32
                try:
                    _restore_window_by_title('Detector de Cor')
                except Exception:
                    try:
                        cv2.moveWindow('Detector de Cor', 100, 100)
                    except Exception:
                        pass

                # Garantir que qualquer clique preso seja solto e flags limpas
                if globals().get('left_down', False):
                    try:
                        _mouse_up('left')
                    except Exception:
                        pass
                    globals()['left_down'] = False
                if globals().get('right_down', False):
                    try:
                        _mouse_up('right')
                    except Exception:
                        pass
                    globals()['right_down'] = False

                # Resetar suavização para evitar saltos do cursor
                prev_mouse_pos = None

                print('→ Interface restaurada. Modo mouse virtual desativado.')
        # Suporte a ações globais de tecla quando a janela está fora de foco
        # (Ex: ESC para sair, 0 para restaurar/alternar modo, R para reset)
        if _use_keyboard:
            try:
                now = time.time()
                if now - last_key_action_time > KEY_DEBOUNCE:
                    # ESC => sair
                    if keyboard.is_pressed('esc') and not prev_key_states.get('esc', False):
                        prev_key_states['esc'] = True
                        last_key_action_time = now
                        break
                    # 0 => togglear modo minimizado/virtual
                    if keyboard.is_pressed('0') and not prev_key_states.get('0', False):
                        prev_key_states['0'] = True
                        last_key_action_time = now
                        window_minimized = not window_minimized
                        virtual_mouse_enabled = window_minimized
                        if window_minimized:
                            try:
                                cv2.moveWindow('Detector de Cor', -2000, -2000)
                            except Exception:
                                pass
                            print('→ MODO MOUSE VIRTUAL ATIVADO (janela escondida). Teclas: a=left, l=right, 0=restaurar')
                        else:
                            try:
                                _restore_window_by_title('Detector de Cor')
                            except Exception:
                                try:
                                    cv2.moveWindow('Detector de Cor', 100, 100)
                                except Exception:
                                    pass

                            # Garantir que qualquer clique preso seja solto e flags limpas
                            if globals().get('left_down', False):
                                try:
                                    _mouse_up('left')
                                except Exception:
                                    pass
                                globals()['left_down'] = False
                            if globals().get('right_down', False):
                                try:
                                    _mouse_up('right')
                                except Exception:
                                    pass
                                globals()['right_down'] = False

                            prev_mouse_pos = None
                            print('→ Interface restaurada. Modo mouse virtual desativado.')
                    # R => reset
                    if keyboard.is_pressed('r') and not prev_key_states.get('r', False):
                        prev_key_states['r'] = True
                        last_key_action_time = now
                        hsv_color = None
                        last_position = None
                        frames_sem_deteccao = 0
                        tolerance_bonus = 0
                        print("\n✓ Reset! Clique em um objeto para começar...\n")

                # Atualizar estados quando teclas são liberadas
                if not keyboard.is_pressed('esc'):
                    prev_key_states['esc'] = False
                if not keyboard.is_pressed('0'):
                    prev_key_states['0'] = False
                if not keyboard.is_pressed('r'):
                    prev_key_states['r'] = False
            except Exception:
                # Se o hook global falhar, ignorar e continuar (apenas cv2.waitKey ficará disponível)
                pass
        # If keyboard module is available, support press-and-hold for a and l
        if _use_keyboard:
            try:
                # Left button hold
                if keyboard.is_pressed('a'):
                    if not globals().get('left_down', False):
                        _mouse_down('left')
                        globals()['left_down'] = True
                else:
                    if globals().get('left_down', False):
                        _mouse_up('left')
                        globals()['left_down'] = False

                # Right button hold
                if keyboard.is_pressed('l'):
                    if not globals().get('right_down', False):
                        _mouse_down('right')
                        globals()['right_down'] = True
                else:
                    if globals().get('right_down', False):
                        _mouse_up('right')
                        globals()['right_down'] = False
            except Exception:
                # If keyboard hook fails, silently ignore and fallback to single clicks
                pass
        
        # FPS control
        fim_frame = cv2.getTickCount()
        tempo_frame = (fim_frame - inicio_frame) / tick_freq
        delay = max(1, int((1.0 / 30 - tempo_frame) * 1000))
    
    # Limpar
    cap.release()
    cv2.destroyAllWindows()
    
    print("\n✓ Detector finalizado!")

if __name__ == "__main__":
    main()
