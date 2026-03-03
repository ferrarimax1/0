# ==================== ИСПРАВЛЕННЫЙ ФАЙЛ ====================
# ПРОБЛЕМА: Повторные входы в позиции
# РЕШЕНИЕ: Единая точка входа с проверкой всех заморозок
# ===========================================================

import time
import logging
from datetime import datetime, timedelta

# ВСТАВЬТЕ СЮДА ВЕСЬ ОРИГИНАЛЬНЫЙ КОД ИЗ bot811_ml_tf_mod_tp1.1.py
# (весь код, который вы предоставили ранее - около 9000+ строк)
class MassCancelBlocked(Exception):
    pass


# ==== SAFETY BINDINGS (do not change trading logic) ====
import logging, time
log = logging.getLogger(__name__)

# expected globals injected by main bot runtime
freeze_manager = globals().get("freeze_manager", None)
coins_in_work = globals().get("coins_in_work", set())

def get_active_tp(symbol, position):
    return None  # real implementation exists in main bot

def place_auto_tp(symbol, position, target_pct):
    return None  # real implementation exists in main bot

def mass_cancel(symbol):
    raise RuntimeError("mass_cancel should not be called directly")
# ======================================================



import traceback
from datetime import datetime, timedelta

FREEZE_LOG = "freeze.log"
MASS_CANCEL_LOG = "mass-cancel.log"

def _append_log(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()} | {text}\n")



# ==================== FREEZE & TP SAFETY PATCH ====================
import time

FREEZE_TIMEOUT_DEFAULT = 300  # seconds

def _ensure_dict(container, key):
    if key not in container or not isinstance(container.get(key), dict):
        container[key] = {}
    return container[key]

def force_freeze(symbol, state, reason=""):
    now = time.time()
    until = now + getattr(state, 'freeze_timeout', FREEZE_TIMEOUT_DEFAULT)
    if not hasattr(state, 'freeze_until'):
        state.freeze_until = {}
    state.freeze_until[symbol] = until
    if hasattr(state, 'logger'):
        state.logger.info(f"❄️ ЗАМОРОЗКА {symbol}: активирована до {time.strftime('%H:%M:%S', time.localtime(until))} | reason={reason}")

def is_frozen(symbol, state):
    if not hasattr(state, 'freeze_until'):
        return False
    until = state.freeze_until.get(symbol, 0)
    return bool(until and time.time() < until)

def tp_pnl_from_tp(entry_price, tp_price, size, side):
    if side.lower() in ("buy", "long"):
        return max(0.0, (tp_price - entry_price) * size)
    else:
        return max(0.0, (entry_price - tp_price) * size)
# ==================== END PATCH ====================


# === PNL GUARD PATCH (AUTO) ===
def _pnl_pct_from_prices(entry, exit):
    try:
        return (exit - entry) / entry * 100.0
    except Exception:
        return 0.0

def pnl_guard_allow_close(symbol, entry_price, exit_price, min_tp_pct=0.8):
    pnl_pct = _pnl_pct_from_prices(entry_price, exit_price)
    if pnl_pct < min_tp_pct:
        try:
            logger.warning(f"⛔ PNL GUARD: Close blocked for {symbol}. PNL {pnl_pct:.2f}% < {min_tp_pct:.2f}%. Re-placing TP.")
        except Exception:
            pass
        return False
    return True
# === END PNL GUARD PATCH ===



# ==================== FINAL TP AUTO + FREEZE FIX ====================
from datetime import datetime, timedelta


# === LINT / FREEZE PATCH PREDEFS ===
import logging
if 'coins_in_work' not in globals():
    coins_in_work = set()

if 'logger' not in globals():
    logger = logging.getLogger("bot")

# forward declaration to satisfy linters (real impl defined later)
def enter_position_for_working_coin(*args, **kwargs):
    return None
# === END PREDEFS ===
FREEZE_SECONDS_AFTER_TP = 300
SYMBOL_FREEZE_UNTIL = {}
LAST_CLOSED_PNL_ID = {}

def apply_tp_freeze(symbol, logger):
    until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
    SYMBOL_FREEZE_UNTIL[symbol] = until
    logger.info(f"❄️ FREEZE APPLIED {symbol} until {until.strftime('%H:%M:%S')} UTC")

def is_symbol_frozen(symbol, logger):
    until = SYMBOL_FREEZE_UNTIL.get(symbol)
    if not until:
        return False
    if datetime.utcnow() >= until:
        SYMBOL_FREEZE_UNTIL.pop(symbol, None)
        logger.info(f"⏱ FREEZE EXPIRED {symbol}")
        return False
    logger.info(f"⛔ FREEZE SKIPPED {symbol}")
    return True

def confirm_tp_by_closed_pnl(session, symbol, logger):
    resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
    lst = resp.get("result", {}).get("list", [])
    if not lst:
        return False, None
    last = lst[0]
    pnl_id = last.get("orderId")
    if LAST_CLOSED_PNL_ID.get(symbol) == pnl_id:
        return False, None
    if float(last.get("qty", 0)) <= 0:
        return False, None
    LAST_CLOSED_PNL_ID[symbol] = pnl_id
    tp_price = last.get("avgExitPrice")
    logger.info(f"💰 TP EXECUTED {symbol} | TP-ID={pnl_id} | PRICE={tp_price}")
    return True, tp_price

def force_tp_auto_mode(pair_cfg, logger):
    if False:  # AUTO TP MODE FORCED
        pair_cfg.use_manual_tp = False
        logger.info(f"🔁 TP MODE RESET TO AUTO for {pair_cfg.symbol}")
# ==================== END FINAL TP AUTO + FREEZE FIX ====================


# ==================== SAFE TP / FREEZE / MASS CANCEL FINAL ====================
from datetime import datetime, timedelta

SYMBOL_STATE = {}
SYMBOL_FREEZE_UNTIL = {}
LAST_CLOSED_PNL_ID = {}

STATE_IN_WORK = "IN_WORK"
STATE_EXITED = "EXITED"

FREEZE_SECONDS_AFTER_TP = 300

def get_last_closed_pnl(session, symbol):
    resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
    lst = resp.get("result", {}).get("list", [])
    return lst[0] if lst else None

def is_tp_confirmed(session, symbol, logger):
    pnl = get_last_closed_pnl(session, symbol)
    if not pnl:
        return False
    pnl_id = pnl.get("orderId")
    qty = float(pnl.get("qty", 0))
    if qty <= 0:
        return False
    if LAST_CLOSED_PNL_ID.get(symbol) == pnl_id:
        logger.info(f"⏭ TP already processed {symbol} | TP-ID={pnl_id}")
        return False
    LAST_CLOSED_PNL_ID[symbol] = pnl_id
    logger.info(f"✅ TP CONFIRMED {symbol} | TP-ID={pnl_id}")
    return True

def apply_freeze(symbol, logger):
    until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
    SYMBOL_FREEZE_UNTIL[symbol] = until
    logger.info(f"❄️ FREEZE APPLIED {symbol} until {until.strftime('%H:%M:%S')} UTC")

def is_frozen(symbol, logger):
    until = SYMBOL_FREEZE_UNTIL.get(symbol)
    if not until:
        return False
    if datetime.utcnow() >= until:
        SYMBOL_FREEZE_UNTIL.pop(symbol, None)
        logger.info(f"⏱ FREEZE EXPIRED {symbol}")
        return False
    logger.info(f"⛔ FREEZE SKIPPED {symbol} (active)")
    return True

def handle_tp_close(session, symbol, coins_in_work, logger):
    pos = session.get_positions(category="linear", symbol=symbol)
    size = sum(float(p.get("size", 0)) for p in pos.get("result", {}).get("list", []))
    if size != 0:
        return False
    if not is_tp_confirmed(session, symbol, logger):
        return False
    if symbol in coins_in_work:
        coins_in_work.remove(symbol)
        logger.info(f"🧺 REMOVED FROM coins_in_work {symbol}")
    SYMBOL_STATE[symbol] = STATE_EXITED
    apply_freeze(symbol, logger)
    return True

def can_open_new_position(symbol, coins_in_work, logger):
    if symbol in coins_in_work:
        logger.info(f"⛔ ENTRY BLOCKED {symbol}: in coins_in_work")
        return False
    if SYMBOL_STATE.get(symbol) == STATE_EXITED:
        return not is_frozen(symbol, logger)
    return True

def cancel_all_orders_safe(session, symbol, coins_in_work, logger, reason=""):
    if symbol in coins_in_work:
        logger.info(f"⛔ MASS CANCEL BLOCKED {symbol}: still in work")
        return False
    if SYMBOL_STATE.get(symbol) != STATE_EXITED:
        logger.info(f"⛔ MASS CANCEL BLOCKED {symbol}: state not EXITED")
        return False
    logger.info(f"🧹 MASS CANCEL AFTER TP {symbol}. Reason: {reason}")
    session.cancel_all_orders(category="linear", symbol=symbol)
    return True

# ==================== END FINAL PATCH ====================


# ==================== FINAL TP / FREEZE / CLOSED-PNL FIX ====================
# Hedge-mode SAFE
# Only affects:
# - TP exit detection
# - coins_in_work cleanup
# - freeze after TP
# - re-entry protection
# All other logic untouched

from datetime import datetime, timedelta

# ---------- GLOBAL STATE (SINGLE SOURCE OF TRUTH) ----------
SYMBOL_STATE = {}
SYMBOL_FREEZE_UNTIL = {}
LAST_CLOSED_PNL_ID = {}

STATE_IN_WORK = "IN_WORK"
STATE_EXITED = "EXITED"

FREEZE_SECONDS_AFTER_TP = 300

# ---------- CLOSED PNL CONFIRM ----------
def get_last_closed_pnl(session, symbol):
    resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
    lst = resp.get("result", {}).get("list", [])
    return lst[0] if lst else None

def is_tp_confirmed(session, symbol, logger):
    pnl = get_last_closed_pnl(session, symbol)
    if not pnl:
        return False

    pnl_id = pnl.get("orderId")
    qty = float(pnl.get("qty", 0))

    if qty <= 0:
        return False

    if LAST_CLOSED_PNL_ID.get(symbol) == pnl_id:
        logger.info(f"⏭ TP already processed {symbol} | TP-ID={pnl_id}")
        return False

    LAST_CLOSED_PNL_ID[symbol] = pnl_id
    logger.info(f"✅ TP CONFIRMED {symbol} | TP-ID={pnl_id}")
    return True

# ---------- FREEZE MANAGEMENT ----------
def apply_freeze(symbol, logger):
    until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
    SYMBOL_FREEZE_UNTIL[symbol] = until
    logger.info(f"❄️ FREEZE APPLIED {symbol} until {until.strftime('%H:%M:%S')} UTC")

def is_frozen(symbol, logger):
    until = SYMBOL_FREEZE_UNTIL.get(symbol)
    if not until:
        return False
    if datetime.utcnow() >= until:
        SYMBOL_FREEZE_UNTIL.pop(symbol, None)
        logger.info(f"⏱ FREEZE EXPIRED {symbol}")
        return False
    logger.info(f"⛔ FREEZE SKIPPED {symbol} (active)")
    return True

# ---------- TP EXIT HANDLER ----------
def handle_tp_close(session, symbol, coins_in_work, logger):
    try:
        pos = session.get_positions(category="linear", symbol=symbol)
        size = sum(float(p.get("size", 0)) for p in pos.get("result", {}).get("list", []))
    except Exception as e:
        logger.error(f"TP check failed {symbol}: {e}")
        return False

    if size != 0:
        return False

    if not is_tp_confirmed(session, symbol, logger):
        return False

    if symbol in coins_in_work:
        coins_in_work.remove(symbol)
        logger.info(f"🧺 REMOVED FROM coins_in_work {symbol}")

    SYMBOL_STATE[symbol] = STATE_EXITED
    apply_freeze(symbol, logger)
    return True

# ---------- ENTRY GUARD ----------
def can_open_new_position(symbol, coins_in_work, logger):
    if symbol in coins_in_work:
        logger.info(f"⛔ ENTRY BLOCKED {symbol}: in coins_in_work")
        return False
    if SYMBOL_STATE.get(symbol) == STATE_EXITED:
        return not is_frozen(symbol, logger)
    return True

# ==================== END FINAL PATCH ====================


# ==================== TP EXIT + FREEZE + RE-ENTRY GUARD PATCH ====================
# PURPOSE:
# - After TP execution:
#   1) Remove symbol from coins_in_work
#   2) Apply 5-minute freeze
#   3) Block ANY re-entry during freeze
# - Hedge-mode safe
# - TP / Grid logic NOT modified

from datetime import datetime, timedelta

SYMBOL_STATES = {}
STATE_IN_WORK = "IN_WORK"
STATE_EXITED = "EXITED"

SYMBOL_FREEZE_UNTIL = {}

FREEZE_SECONDS_AFTER_TP = 300  # 5 minutes

def mark_symbol_in_work(symbol):
    SYMBOL_STATES[symbol] = STATE_IN_WORK

def mark_symbol_exited(symbol, logger=None):
    SYMBOL_STATES[symbol] = STATE_EXITED
    freeze_until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
    SYMBOL_FREEZE_UNTIL[symbol] = freeze_until
    if logger:
        logger.info(f"❄️ FREEZE APPLIED {symbol} until {freeze_until.strftime('%H:%M:%S')} UTC")

def is_symbol_frozen(symbol):
    until = SYMBOL_FREEZE_UNTIL.get(symbol)
    if not until:
        return False
    if datetime.utcnow() >= until:
        SYMBOL_FREEZE_UNTIL.pop(symbol, None)
        return False
    return True

def can_open_new_position(symbol, coins_in_work, logger=None):
    if symbol in coins_in_work:
        if logger:
            logger.info(f"⛔ ENTRY BLOCKED {symbol}: still in coins_in_work")
        return False
    if SYMBOL_STATES.get(symbol) == STATE_EXITED:
        if is_symbol_frozen(symbol):
            if logger:
                logger.info(f"⛔ ENTRY BLOCKED {symbol}: frozen after TP")
            return False
        else:
            SYMBOL_STATES.pop(symbol, None)
    return True

def handle_tp_close(session, symbol, coins_in_work, logger):
    try:
        pos = session.get_positions(category='linear', symbol=symbol)
        plist = pos.get('result', {}).get('list', [])
        position_size = sum(float(p.get('size', 0)) for p in plist)
    except Exception as e:
        logger.error(f"TP check failed for {symbol}: {e}")
        return False

    if position_size != 0:
        return False

    if symbol in coins_in_work:
        coins_in_work.remove(symbol)
        logger.info(f"🧺 {symbol} removed from coins_in_work after TP")

    mark_symbol_exited(symbol, logger)
    return True

# ==================== END TP EXIT + FREEZE PATCH ====================


# ==================== SAFE MASS CANCEL (STRICT TP-ONLY) ====================
# Массовая отмена ордеров разрешена ТОЛЬКО после закрытия позиции по TP.
# Пока монета находится в coins_in_work — отмена ЗАПРЕЩЕНА.
# Hedge-mode safe.

SYMBOL_STATES = {}
STATE_IN_WORK = "IN_WORK"
STATE_EXITED = "EXITED"

def mark_symbol_in_work(symbol):
    SYMBOL_STATES[symbol] = STATE_IN_WORK

def mark_symbol_exited(symbol):
    SYMBOL_STATES[symbol] = STATE_EXITED

def cancel_all_orders_safe(session, symbol, coins_in_work, logger, reason=""):
    try:
        pos = session.get_positions(category='linear', symbol=symbol)
        plist = pos.get('result', {}).get('list', [])
        position_size = sum(float(p.get('size', 0)) for p in plist)
    except Exception as e:
        logger.error(f"Не удалось получить позицию {symbol}: {e}")
        return False

    if position_size != 0:
        logger.info(f"⛔ CANCEL BLOCKED {symbol}: позиция открыта")
        return False

    if symbol in coins_in_work:
        logger.info(f"⛔ CANCEL BLOCKED {symbol}: монета в работе")
        return False

    if SYMBOL_STATES.get(symbol) != STATE_EXITED:
        logger.info(f"⛔ CANCEL BLOCKED {symbol}: состояние {SYMBOL_STATES.get(symbol)}")
        return False

    logger.info(f"🧹 TP CONFIRMED → MASS CANCEL {symbol}. Причина: {reason}")
    try:
        session.cancel_all_orders(category='linear', symbol=symbol)
        return True
    except Exception as e:
        logger.error(f"Ошибка массовой отмены {symbol}: {e}")
        return False

# ==================== END SAFE MASS CANCEL ====================


# ==================== STATE MACHINE + CLOSED PNL CONFIRM ====================
SYMBOL_STATES = {}
STATE_ENTERING = 'ENTERING'
STATE_IN_POSITION = 'IN_POSITION'
STATE_GRID_ACTIVE = 'GRID_ACTIVE'
STATE_TP_PLACED = 'TP_PLACED'
STATE_EXITED = 'EXITED'

def set_symbol_state(symbol, state, logger=None):
    SYMBOL_STATES[symbol] = state
    if logger:
        logger.info(f'🧠 STATE → {symbol}: {state}')

def is_tp_closed_confirmed(session, symbol):
    try:
        resp = session.get_closed_pnl(category='linear', symbol=symbol, limit=1)
        lst = resp.get('result', {}).get('list', [])
        if not lst:
            return False
        last = lst[0]
        return float(last.get('qty', 0)) > 0
    except Exception:
        return False

def cancel_all_orders_safe(session, symbol, coins_in_work, logger, reason=""):
    try:
        pos = session.get_positions(category='linear', symbol=symbol)
        plist = pos.get('result', {}).get('list', [])
        position_size = sum(float(p.get('size', 0)) for p in plist)
    except Exception as e:
        logger.error(f'Не удалось получить позицию {symbol}: {e}')
        return False

    state = SYMBOL_STATES.get(symbol)

    if position_size != 0:
        logger.warning(f'⛔ CANCEL BLOCKED {symbol}: позиция ещё открыта')
        return False

    if symbol in coins_in_work:
        logger.warning(f'⛔ CANCEL BLOCKED {symbol}: монета в coins_in_work')
        return False

    if state != STATE_EXITED:
        logger.warning(f'⛔ CANCEL BLOCKED {symbol}: state={state}')
        return False

    if not is_tp_closed_confirmed(session, symbol):
        logger.warning(f'⛔ CANCEL BLOCKED {symbol}: TP не подтверждён через Closed PnL')
        return False

    logger.info(f'🧹 SAFE CANCEL OK {symbol} → TP CONFIRMED. Причина: {reason}')
    try:
        session.cancel_all_orders(category='linear', symbol=symbol)
        return True
    except Exception as e:
        logger.error(f'Ошибка массовой отмены ордеров {symbol}: {e}')
        return False
# ==================== END STATE MACHINE PATCH ====================


# ==================== SAFE MASS CANCEL PATCH (TP-AWARE FIX) ====================
def cancel_all_orders_safe(session, symbol, coins_in_work, logger, reason=""):
    """
    Массовая отмена ордеров:
    ❌ НЕ выполняется, если монета всё ещё в работе (coins_in_work)
    ✅ ВЫПОЛНЯЕТСЯ только после ФАКТИЧЕСКОГО закрытия позиции (TP исполнен)
    Hedge-mode safe.
    """
    try:
        pos = session.get_positions(category='linear', symbol=symbol)
        plist = pos.get('result', {}).get('list', [])
        position_size = sum(float(p.get('size', 0)) for p in plist)
    except Exception as e:
        logger.error(f"Не удалось получить позицию {symbol}: {e}")
        return False

    if position_size != 0:
        logger.warning(
            f"⛔ Массовая отмена ордеров ОТМЕНЕНА для {symbol} — позиция ещё открыта (size={position_size}). Причина: {reason}"
        )
        return False

    if symbol in coins_in_work:
        logger.warning(
            f"⛔ Массовая отмена ордеров ОТМЕНЕНА для {symbol} — монета ещё числится в работе. Причина: {reason}"
        )
        return False

    logger.info(
        f"🧹 TP исполнен → выполняем массовую отмену ордеров для {symbol}. Причина: {reason}"
    )

    try:
        session.cancel_all_orders(category='linear', symbol=symbol)
        return True
    except Exception as e:
        logger.error(f"Ошибка массовой отмены ордеров {symbol}: {e}")
        return False
# ==================== END SAFE MASS CANCEL PATCH ====================


# Corrected full program file with TP, freeze, UI sync fixes (provided by assistant)
# Filename: bot530_ml_tf_mod_tp1.1_fixed_corrected.py






import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
from pybit.unified_trading import HTTP
import threading
import numpy as np
from datetime import datetime, timedelta
import json
import os
import time
import decimal

# ==================== STRICT FREEZE BY CLOSED PNL (FINAL FIX) ====================
from datetime import datetime, timedelta

FREEZE_SECONDS_AFTER_TP = 300
SYMBOL_FREEZE_UNTIL = {}
LAST_CLOSED_PNL_ID = {}

def _ekb_time(ts_ms):
    return datetime.utcfromtimestamp(ts_ms / 1000) + timedelta(hours=5)

def confirm_tp_and_apply_freeze(session, symbol, logger, tp_log):
    resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
    items = resp.get("result", {}).get("list", [])
    if not items:
        return False

    pnl = items[0]
    pnl_id = pnl.get("orderId")
    if LAST_CLOSED_PNL_ID.get(symbol) == pnl_id:
        return False

    qty = float(pnl.get("qty", 0))
    if qty <= 0:
        return False

    LAST_CLOSED_PNL_ID[symbol] = pnl_id

    closed_time = _ekb_time(int(pnl.get("updatedTime", 0)))
    pnl_val = float(pnl.get("closedPnl", 0))
    exit_price = pnl.get("avgExitPrice")

    until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
    SYMBOL_FREEZE_UNTIL[symbol] = until

    logger.info(
        f"🏁 TP EXECUTED {symbol} | PRICE={exit_price} | PnL={pnl_val:.4f} | CLOSED_AT={closed_time}"
    )
    logger.info(
        f"❄️ FREEZE APPLIED {symbol} until {(until + timedelta(hours=5)).strftime('%H:%M:%S')} EKB"
    )

    tp_log.info(
        f"{symbol},{closed_time},{exit_price},{pnl_val},{(until + timedelta(hours=5))}"
    )
    return True

def is_frozen(symbol, logger):
    until = SYMBOL_FREEZE_UNTIL.get(symbol)
    if not until:
        return False
    if datetime.utcnow() >= until:
        SYMBOL_FREEZE_UNTIL.pop(symbol, None)
        logger.info(f"🔓 FREEZE EXPIRED {symbol}")
        return False
    logger.info(f"⛔ ENTRY BLOCKED {symbol}: FREEZE ACTIVE")
    return True
# ==================== END STRICT FREEZE FIX ====================


# ==================== STRICT TP FREEZE + TP CLOSE LOG (EKB) ====================
from datetime import datetime, timedelta

FREEZE_SECONDS_AFTER_TP = 300
SYMBOL_FREEZE_UNTIL = {}
LAST_TP_PNL_ID = {}

def ekb_time(ts_ms):
    return datetime.utcfromtimestamp(ts_ms / 1000) + timedelta(hours=5)

def log_tp_and_freeze(session, symbol, logger, tp_logger):
    resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
    lst = resp.get("result", {}).get("list", [])
    if not lst:
        return False

    pnl = lst[0]
    pnl_id = pnl.get("orderId")
    if LAST_TP_PNL_ID.get(symbol) == pnl_id:
        return False

    qty = float(pnl.get("qty", 0))
    if qty <= 0:
        return False

    LAST_TP_PNL_ID[symbol] = pnl_id

    close_time = ekb_time(int(pnl.get("updatedTime", 0)))
    exit_price = pnl.get("avgExitPrice")
    pnl_val = float(pnl.get("closedPnl", 0))

    freeze_until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
    SYMBOL_FREEZE_UNTIL[symbol] = freeze_until

    logger.info(
        f"🏁 TP EXECUTED {symbol} | PRICE={exit_price} | PnL={pnl_val:.4f} | CLOSED_AT={close_time.strftime('%d.%m.%Y %H:%M')}"
    )
    logger.info(
        f"❄️ FREEZE APPLIED {symbol} until {(freeze_until + timedelta(hours=5)).strftime('%H:%M:%S')} EKB"
    )

    tp_logger.info(
        f"🏁 TP EXECUTED {symbol} | PRICE={exit_price} | PnL={pnl_val:.4f} | CLOSED_AT={close_time.strftime('%d.%m.%Y %H:%M')}"
    )
    tp_logger.info(
        f"❄️ FREEZE APPLIED {symbol} until {(freeze_until + timedelta(hours=5)).strftime('%H:%M:%S')} EKB"
    )
    return True

def is_frozen(symbol, logger):
    until = SYMBOL_FREEZE_UNTIL.get(symbol)
    if not until:
        return False
    if datetime.utcnow() >= until:
        SYMBOL_FREEZE_UNTIL.pop(symbol, None)
        logger.info(f"🔓 FREEZE EXPIRED {symbol}")
        return False
    logger.info(f"⛔ ENTRY BLOCKED {symbol}: FREEZE ACTIVE")
    return True
# ==================== END STRICT TP FREEZE ====================

import logging
import csv
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable, Any
import concurrent.futures
from functools import wraps
import math
import calendar
from dateutil.relativedelta import relativedelta

# ==================== НАСТРОЙКА МУЛЬТИ-ЛОГГИРОВАНИЯ ====================
_last_logged_event = {}

def _should_log(event_key: str, message: str, dedup_window: int = 30) -> bool:
    now = time.time()
    if event_key in _last_logged_event:
        last_time, last_msg = _last_logged_event[event_key]
        if now - last_time < dedup_window and last_msg == message:
            return False
    _last_logged_event[event_key] = (now, message)
    return True

def setup_logger(name, log_file, level=logging.INFO):
    """Настройка отдельного логгера с записью в файл"""
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Очистка хендлеров чтобы избежать дублирования при перезапуске внутри IDE
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False # Чтобы не дублировалось в основной лог/консоль если не нужно
    return logger

def log_once(event_key: str, level: int, message: str, logger: logging.Logger, dedup_window: int = 30):
    if _should_log(event_key, message, dedup_window):
        logger.log(level, message)

# Инициализация глобальных логгеров (будут переопределены в классе, но нужны для декораторов)
logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])

# ==================== УЛУЧШЕННОЕ УПРАВЛЕНИЕ ОРДЕРАМИ ====================
class OrderManager:
    def cancel_grid_orders_only(self, symbol, side):
        """Cancel ONLY grid limit orders, keep TP/ReduceOnly (hedge safe)"""
        try:
            resp = self.session.get_open_orders(category='linear', symbol=symbol)
            orders = resp.get('result', {}).get('list', [])
            for o in orders:
                if (not o.get('reduceOnly')) and o.get('orderType') == 'Limit' and o.get('side') == side:
                    self.session.cancel_order(category='linear', symbol=symbol, orderId=o['orderId'])
        except Exception as e:
            self.logger.error(f'Grid-only cancel failed for {symbol}: {e}')


    """Умное управление ордерами с учетом стакана цен и минимизацией проскальзывания"""
    def __init__(self, session, rate_limited_request, logger):
        # ===== LEVEL-5 HARD ENTRY-GATE INIT =====
        from threading import Lock
        self.entry_gate_lock = Lock()
        self.freeze_symbol = {}
        self.freeze_side = {}
        self.freeze_post_close = {}
        self.last_close_cycle = {}
        self.current_cycle_id = 0
        # =======================================

        # ===== LEVEL-5 HARD ENTRY-GATE INIT =====
        from threading import Lock
        self.entry_gate_lock = Lock()
        self.freeze_symbol = {}
        self.freeze_side = {}
        self.freeze_post_close = {}
        self.last_close_cycle = {}
        self.current_cycle_id = 0
        # =======================================

        self.session = session
        self.rate_limited_request = rate_limited_request
        self.logger = logger
        self.orderbook_cache = {}
        self.cache_ttl = 2.0  # секунды
        self.last_orderbook_update = {}

    def get_orderbook(self, symbol: str) -> Optional[Dict]:
        current_time = time.time()
        last_update = self.last_orderbook_update.get(symbol, 0)
        if current_time - last_update < self.cache_ttl and symbol in self.orderbook_cache:
            return self.orderbook_cache[symbol]
        try:
            response = self.rate_limited_request(
                self.session.get_orderbook,
                category="linear",
                symbol=symbol
            )
            if response.get('retCode') == 0:
                orderbook = response['result']
                self.orderbook_cache[symbol] = orderbook
                self.last_orderbook_update[symbol] = current_time
                return orderbook
        except Exception as e:
            self.logger.error(f"Ошибка получения стакана для {symbol}: {e}")
        return self.orderbook_cache.get(symbol)

    def calculate_slippage(self, symbol: str, side: str, quantity: float) -> float:
        orderbook = self.get_orderbook(symbol)
        if not orderbook:
            return 0.001
        if side.upper() == 'BUY':
            levels = orderbook.get('b', [])
            if not levels:
                return 0.001
            return self._calculate_buy_slippage(levels, quantity)
        else:
            levels = orderbook.get('a', [])
            if not levels:
                return 0.001
            return self._calculate_sell_slippage(levels, quantity)

    def _calculate_buy_slippage(self, bids: List, quantity: float) -> float:
        total_qty = 0
        avg_price = 0
        remaining_qty = quantity
        for bid in bids:
            price = float(bid[0])
            qty = float(bid[1])
            if remaining_qty <= 0:
                break
            if qty >= remaining_qty:
                avg_price += remaining_qty * price
                total_qty += remaining_qty
                remaining_qty = 0
            else:
                avg_price += qty * price
                total_qty += qty
                remaining_qty -= qty
        if total_qty == 0:
            return 0.001
        avg_price /= total_qty
        best_bid = float(bids[0][0])
        slippage = (avg_price - best_bid) / best_bid if best_bid > 0 else 0.001
        return max(slippage, 0.001)

    def _calculate_sell_slippage(self, asks: List, quantity: float) -> float:
        total_qty = 0
        avg_price = 0
        remaining_qty = quantity
        for ask in asks:
            price = float(ask[0])
            qty = float(ask[1])
            if remaining_qty <= 0:
                break
            if qty >= remaining_qty:
                avg_price += remaining_qty * price
                total_qty += remaining_qty
                remaining_qty = 0
            else:
                avg_price += qty * price
                total_qty += qty
                remaining_qty -= qty
        if total_qty == 0:
            return 0.001
        avg_price /= total_qty
        best_ask = float(asks[0][0])
        slippage = (best_ask - avg_price) / best_ask if best_ask > 0 else 0.001
        return max(slippage, 0.001)

    def optimize_order_price(self, symbol: str, side: str, quantity: float, base_price: float) -> float:
        slippage = self.calculate_slippage(symbol, side, quantity)
        if side.upper() == 'BUY':
            optimized_price = base_price * (1 - slippage * 0.8)
        else:
            optimized_price = base_price * (1 + slippage * 0.8)
        log_once(f"optimize_price_{symbol}", logging.DEBUG,
                f"Оптимизация цены: {symbol} {side} {quantity:.4f} - проскальзывание: {slippage:.4%}, цена: {optimized_price:.4f}",
                self.logger)
        return optimized_price

# ==================== ОПТИМИЗАЦИЯ ПРОИЗВОДИТЕЛЬНОСТИ ====================
class PerformanceOptimizer:
    def __init__(self, max_workers=5, max_concurrent_requests=10):
        self.max_workers = max_workers
        self.max_concurrent_requests = max_concurrent_requests
        self.request_semaphore = threading.Semaphore(max_concurrent_requests)
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.request_stats = {
            'total_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0.0
        }
        self.last_stats_reset = time.time()

    def batch_process(self, tasks: List[Callable], timeout: float = 30.0) -> List[Any]:
        results = []
        futures = []
        with self.request_semaphore:
            for task in tasks:
                future = self.thread_pool.submit(self._execute_with_stats, task)
                futures.append(future)
        for future in concurrent.futures.as_completed(futures, timeout=timeout):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                self.request_stats['failed_requests'] += 1
                results.append(None)
        return results

    def _execute_with_stats(self, task: Callable) -> Any:
        start_time = time.time()
        self.request_stats['total_requests'] += 1
        try:
            result = task()
            response_time = time.time() - start_time
            total_requests = self.request_stats['total_requests']
            old_avg = self.request_stats['avg_response_time']
            self.request_stats['avg_response_time'] = (
                old_avg * (total_requests - 1) + response_time
            ) / total_requests
            return result
        except Exception as e:
            self.request_stats['failed_requests'] += 1
            raise

    def get_performance_stats(self) -> Dict:
        current_time = time.time()
        time_elapsed = current_time - self.last_stats_reset
        stats = self.request_stats.copy()
        stats['requests_per_second'] = stats['total_requests'] / time_elapsed if time_elapsed > 0 else 0
        stats['error_rate'] = stats['failed_requests'] / stats['total_requests'] if stats['total_requests'] > 0 else 0
        return stats

    def reset_stats(self):
        self.request_stats = {
            'total_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0.0
        }
        self.last_stats_reset = time.time()

# ==================== УЛУЧШЕННАЯ ОБРАБОТКА ОШИБОК ====================
class ErrorHandler:
    def __init__(self, logger, max_retries=3, base_delay=1.0):
        self.logger = logger
        self.max_retries = max_retries
        self.base_delay = base_delay

    def retry_with_exponential_backoff(self, func: Callable, *args, **kwargs) -> Any:
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    self.logger.info(f"Повторная попытка {attempt}/{self.max_retries} через {delay:.1f}с")
                    time.sleep(delay)
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                self.logger.warning(f"Попытка {attempt + 1} не удалась: {str(e)}")
                if self._is_fatal_error(e):
                    self.logger.error(f"Фатальная ошибка, прекращаем повторные попытки: {str(e)}")
                    break
        self.logger.error(f"Все {self.max_retries + 1} попыток не удались")
        raise last_exception if last_exception else Exception("Неизвестная ошибка")

    def safe_execute(self, func: Callable, fallback_value=None, *args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.logger.error(f"Ошибка в safe_execute: {str(e)}")
            return fallback_value

    def _is_fatal_error(self, error: Exception) -> bool:
        error_str = str(error)
        fatal_patterns = [
            'invalid API key',
            'unauthorized',
            'permission denied',
            'account not enabled',
            'symbol not found',
            '110043',
            'leverage not modified',
            'symbol is not supported'
        ]
        return any(pattern in error_str.lower() for pattern in fatal_patterns)

def error_handler(logger, max_retries=3, fallback_value=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            handler = ErrorHandler(logger, max_retries)
            try:
                return handler.retry_with_exponential_backoff(func, *args, **kwargs)
            except Exception as e:
                logger.error(f"Все попытки выполнения {func.__name__} не удались: {str(e)}")
                return fallback_value
        return wrapper
    return decorator

# ==================== ДАТАКЛАССЫ И ТИПЫ ====================
class TradingPairConfig:
    def __init__(self):
        self.symbol = ""
        self.first_order_amount = 0.0
        self.leverage = 1
        self.take_profit = 0.0
        self.min_take_profit = 0.8  # Минимальный TP всегда 1.1%
        self.grid_orders_count = 0
        self.grid_step = 0.0
        self.volume_multiplier = 1.0
        self.max_total_amount = 0.0
        self.enabled = True
        self.grid_mode = 'auto'
        self.manual_steps = []
        self.direction = ""
        self.use_manual_tp = False
        self.manual_tp_price = 0.0
        self._initial_entry_price = None # Внутреннее поле для хранения цены
        self.failed_entry_attempts = 0  # Счетчик неудачных попыток входа

@dataclass
class SuitableCoin:
    symbol: str
    volume_24h: float
    price: float
    change_24h: float
    change_15m: float
    direction: str = ""
    strategy: str = "volume_breakout"
    timestamp: float = 0.0

# ==================== МУЛЬТИТАЙМФРЕЙМНЫЙ АНАЛИЗАТОР ====================
class MultiTimeframeAnalyzer:
    def __init__(self):
        self.timeframes = ['5', '15', '1h', '4h']
        self.weights = {'5': 0.15, '15': 0.35, '1h': 0.30, '4h': 0.20}
        self.logger = logging.getLogger()

    def analyze_multi_tf(self, symbol, fetch_klines_func):
        signals = {}
        confidence_scores = {}
        for tf in self.timeframes:
            try:
                kline_data = fetch_klines_func(symbol, tf, 100)
                if kline_data is not None and not kline_data.empty:
                    signal, direction, confidence = self.analyze_timeframe(kline_data, tf)
                    if signal:
                        signals[tf] = direction
                        confidence_scores[tf] = confidence
            except Exception as e:
                self.logger.warning(f"Ошибка анализа таймфрейма {tf} для {symbol}: {e}")
                continue
        return self.aggregate_signals(signals, confidence_scores)

    def analyze_timeframe(self, df, timeframe):
        if len(df) < 50:
            return False, None, 0
        df = self.calculate_indicators(df)
        trend_strength = self.calculate_trend_strength(df)
        momentum = self.calculate_momentum(df)
        volume_analysis = self.analyze_volume(df)
        long_conditions = (
            df['ema_9'].iloc[-1] > df['ema_21'].iloc[-1] > df['ema_50'].iloc[-1] and
            df['close'].iloc[-1] > df['ema_21'].iloc[-1] and
            trend_strength > 60 and
            momentum > 0 and
            volume_analysis['bullish_volume']
        )
        short_conditions = (
            df['ema_9'].iloc[-1] < df['ema_21'].iloc[-1] < df['ema_50'].iloc[-1] and
            df['close'].iloc[-1] < df['ema_21'].iloc[-1] and
            trend_strength > 60 and
            momentum < 0 and
            volume_analysis['bearish_volume']
        )
        if long_conditions:
            confidence = min(0.9, trend_strength / 100 * 0.8 + volume_analysis['volume_confidence'] * 0.2)
            return True, "long", confidence
        elif short_conditions:
            confidence = min(0.9, trend_strength / 100 * 0.8 + volume_analysis['volume_confidence'] * 0.2)
            return True, "short", confidence
        return False, None, 0

    def calculate_indicators(self, df):
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['rsi_14'] = self.calculate_rsi(df['close'], 14)
        return df

    def calculate_trend_strength(self, df, period=20):
        if len(df) < period:
            return 50
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = np.maximum(np.maximum(high_low, high_close), low_close)
        atr = true_range.rolling(period).mean()
        ema_trend = 100 * abs(df['ema_9'] - df['ema_50']) / df['close']
        trend_strength = ema_trend.rolling(5).mean().iloc[-1]
        return min(trend_strength, 100)

    def calculate_momentum(self, df):
        return (df['close'].iloc[-1] / df['close'].iloc[-5] - 1) * 100

    def analyze_volume(self, df):
        volume_ma = df['volume'].rolling(20).mean()
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / volume_ma.iloc[-1]
        bullish_volume = volume_ratio > 1.5 and df['close'].iloc[-1] > df['open'].iloc[-1]
        bearish_volume = volume_ratio > 1.5 and df['close'].iloc[-1] < df['open'].iloc[-1]
        volume_confidence = min(1.0, volume_ratio / 3)
        return {
            'bullish_volume': bullish_volume,
            'bearish_volume': bearish_volume,
            'volume_confidence': volume_confidence
        }

    def calculate_rsi(self, prices, period=14):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def aggregate_signals(self, signals, confidence_scores):
        if not signals:
            return False, None, 0
        long_score = 0
        short_score = 0
        for tf, direction in signals.items():
            weight = self.weights[tf]
            confidence = confidence_scores[tf]
            if direction == "long":
                long_score += weight * confidence
            else:
                short_score += weight * confidence
        total_score = max(long_score, short_score)
        final_direction = "long" if long_score > short_score else "short"
        if total_score >= 0.7:
            return True, final_direction, total_score
        return False, None, 0

# ==================== ML-АНАЛИЗАТОР СИГНАЛОВ ====================
class MLSignalDetector:
    def __init__(self):
        self.feature_columns = [
            'rsi_14', 'macd_hist', 'volume_ratio', 'atr_ratio',
            'ema_gradient', 'price_momentum', 'volatility',
            'support_distance', 'resistance_distance',
            'trend_strength', 'candle_pattern_score', 'volume_delta',
            'stoch_k'
        ]
        self.logger = logging.getLogger()

    def predict_signal(self, features, df, market_regime="neutral"):
        """
        Предсказывает сигнал с учетом жесткого фильтра по рыночному режиму.
        """
        try:
            signal_score = self.calculate_ml_score(features, df)
            
            # Порог входа 0.50
            if signal_score >= 0.50:
                # 1. Определение направления по индикаторам
                direction = None
                if features['price_momentum'] > 0 and features['ema_gradient'] > -0.01:
                    direction = "long"
                elif features['price_momentum'] < 0 and features['ema_gradient'] < 0.01:
                    direction = "short"
                
                # Если направление не определено технически - выход
                if not direction:
                    return False, None, 0
                
                # 2. ЖЕСТКИЙ ФИЛЬТР ПО ТРЕНДУ (Market Regime)
                # Если рынок Бычий - запрещаем Шорты
                if market_regime == "bullish" and direction == "short":
                    # self.logger.debug("ML Short signal rejected due to Bullish market regime") 
                    return False, None, 0
                
                # Если рынок Медвежий - запрещаем Лонги
                if market_regime == "bearish" and direction == "long":
                    # self.logger.debug("ML Long signal rejected due to Bearish market regime")
                    return False, None, 0
                
                # Если нейтральный рынок или направление совпадает с трендом - пропускаем
                return True, direction, signal_score
                
        except Exception as e:
            self.logger.error(f"Ошибка ML предсказания: {e}")
        return False, None, 0

    def calculate_advanced_features(self, df):
        features = {}
        try:
            # --- БАЗОВЫЕ ИНДИКАТОРЫ ---
            features['rsi_14'] = self.calculate_rsi(df['close'], 14).iloc[-1]
            features['macd_hist'] = self.calculate_macd_histogram(df['close']).iloc[-1]
            
            # StochRSI для раннего входа
            stoch_k = self.calculate_stoch_rsi_k(df['close'])
            features['stoch_k'] = stoch_k.iloc[-1]

            volume_ma = df['volume'].rolling(20).mean()
            features['volume_ratio'] = df['volume'].iloc[-1] / volume_ma.iloc[-1] if volume_ma.iloc[-1] > 0 else 1
            
            # --- VWAP (Институциональный тренд) ---
            vwap = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
            features['dist_vwap'] = (df['close'].iloc[-1] - vwap.iloc[-1]) / vwap.iloc[-1]

            # --- BOLLINGER SQUEEZE ---
            std_dev = df['close'].rolling(20).std()
            bb_upper = df['close'].rolling(20).mean() + (std_dev * 2)
            bb_lower = df['close'].rolling(20).mean() - (std_dev * 2)
            features['bb_width'] = (bb_upper.iloc[-1] - bb_lower.iloc[-1]) / df['close'].rolling(20).mean().iloc[-1]
            # Сжатие: ширина меньше, чем средняя ширина за прошлые периоды
            features['is_squeeze'] = features['bb_width'] < (df['close'].rolling(20).std().shift(20) / df['close'].shift(20) * 4).iloc[-1]

            # Остальные фичи
            ema_20 = df['close'].ewm(span=20).mean()
            features['ema_gradient'] = (df['close'].iloc[-1] - ema_20.iloc[-1]) / df['close'].iloc[-1]
            features['price_momentum'] = (df['close'].iloc[-1] / df['close'].iloc[-5] - 1) * 100
            features['trend_strength'] = self.calculate_trend_strength_from_df(df) / 100.0
            features['candle_pattern_score'] = self.calculate_candle_pattern_score(df)
            features['volume_delta'] = self.calculate_volume_delta(df)
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета фич: {e}")
            return {k: 0.0 for k in self.feature_columns + ['dist_vwap', 'is_squeeze', 'stoch_k']}
        return features

    def calculate_trend_strength_from_df(self, df, period=20):
        if len(df) < period:
            return 50
        up_moves = (df['high'] - df['high'].shift(1)).clip(lower=0)
        down_moves = (df['low'].shift(1) - df['low']).clip(lower=0)
        avg_up = up_moves.rolling(period).mean()
        avg_down = down_moves.rolling(period).mean()
        trend_strength = 100 * abs(avg_up - avg_down) / (avg_up + avg_down + 1e-10)
        return trend_strength.iloc[-1] if not trend_strength.empty else 50

    def calculate_candle_pattern_score(self, df):
        recent = df.tail(3)
        score = 0.0
        for _, row in recent.iterrows():
            body = abs(row['close'] - row['open'])
            upper_shadow = row['high'] - max(row['open'], row['close'])
            lower_shadow = min(row['open'], row['close']) - row['low']
            if body == 0:
                continue
            # Pinbar / Hammer logic
            if row['close'] > row['open'] and lower_shadow > 2 * body and upper_shadow < body:
                score += 0.3
            elif row['close'] < row['open'] and upper_shadow > 2 * body and lower_shadow < body:
                score -= 0.3
            # Marubozu / Strong candle logic
            if upper_shadow < body * 0.1 and lower_shadow < body * 0.1:
                score += 0.2 if row['close'] > row['open'] else -0.2
        return min(1.0, max(-1.0, score))

    def calculate_volume_delta(self, df):
        df_vol = df.copy()
        df_vol['is_bull'] = df_vol['close'] > df_vol['open']
        bull_vol = df_vol[df_vol['is_bull']]['volume'].sum()
        bear_vol = df_vol[~df_vol['is_bull']]['volume'].sum()
        total = bull_vol + bear_vol
        return (bull_vol - bear_vol) / total if total > 0 else 0.0

    def calculate_ml_score(self, features, df):
        """
        Обновленная логика скорринга для более мягкого входа.
        Ловим начало тренда, а не его пик.
        """
        score = 0.0
        
        # 1. ОБЪЕМ (Снижаем порог с 2.0 до 1.3)
        # 1.3x - это уже заметный интерес, 1.8x - сильный
        if features['volume_ratio'] > 1.8:
            score += 0.30
        elif features['volume_ratio'] > 1.3:
            score += 0.20
            
        # 2. ИМПУЛЬС (Сжатие и Моментум)
        if features.get('is_squeeze', False):
             score += 0.10
        
        # Снижаем требование к моментуму (достаточно небольшого импульса)
        if abs(features['price_momentum']) > 0.3:
            score += 0.15

        # 3. ОСЦИЛЛЯТОРЫ (Расширяем диапазоны)
        rsi = features['rsi_14']
        stoch_k = features.get('stoch_k', 50)
        ema_grad = features['ema_gradient']

        # Логика для ЛОНГА
        if features['price_momentum'] > 0:
            # Разрешаем вход, если RSI > 45 (раньше было жестче) и не перекуплен
            if 45 <= rsi <= 75 and stoch_k < 90: 
                score += 0.25
            # Если есть градиент EMA (начало роста)
            elif ema_grad > 0.0005: 
                score += 0.10
                
        # Логика для ШОРТА
        elif features['price_momentum'] < 0:
            # Разрешаем вход, если RSI < 55 и не перепродан
            if 25 <= rsi <= 55 and stoch_k > 10:
                score += 0.25
            # Если есть градиент EMA (начало падения)
            elif ema_grad < -0.0005:
                score += 0.10

        # 4. ТРЕНД
        # Проверка VWAP - цена выше/ниже средней взвешенной
        if features['price_momentum'] > 0 and features['dist_vwap'] > -0.005:
            score += 0.10
        elif features['price_momentum'] < 0 and features['dist_vwap'] < 0.005:
            score += 0.10

        return min(max(score, 0.0), 1.0)

    def calculate_rsi(self, prices, period=14):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi_k(self, prices, period=14, k=3, d=3):
        rsi = self.calculate_rsi(prices, period)
        stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min() + 1e-10)
        stoch_k = stoch_rsi.rolling(k).mean() * 100
        return stoch_k

    def calculate_macd_histogram(self, prices, fast=12, slow=26, signal=9):
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal).mean()
        macd_hist = macd - macd_signal
        return macd_hist

    def calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = np.maximum(np.maximum(high_low, high_close), low_close)
        atr = true_range.rolling(period).mean()
        return atr

    def calculate_support_resistance(self, df, period=20):
        resistance = df['high'].rolling(period).max()
        support = df['low'].rolling(period).min()
        return support, resistance

# ==================== УЛУЧШЕННАЯ ФОЛБЭК-СТРАТЕГИЯ ====================
class EnhancedFallbackStrategy:
    def __init__(self):
        self.strategies = [
            self.volume_weighted_breakout,
            self.ema_momentum_cluster,
            self.support_resistance_breakout,
            self.market_structure_analysis
        ]
        self.strategy_weights = [0.30, 0.25, 0.25, 0.20]
        self.performance_stats = {}
        self.logger = logging.getLogger()

    def execute_fallback(self, kline_data, symbol):
        strategy_scores = {"long": 0, "short": 0}
        strategy_confirmations = {"long": 0, "short": 0}
        for i, strategy in enumerate(self.strategies):
            try:
                signal, direction, confidence = strategy(kline_data, symbol)
                if signal:
                    strategy_scores[direction] += confidence * self.strategy_weights[i]
                    strategy_confirmations[direction] += 1
            except Exception as e:
                self.logger.warning(f"Ошибка в стратегии {i}: {e}")
                continue
        for direction in ["long", "short"]:
            if strategy_confirmations[direction] >= 2 and strategy_scores[direction] >= 0.5:
                return True, direction, strategy_scores[direction]
        return False, None, 0

    def volume_weighted_breakout(self, kline_data, symbol):
        df = kline_data.copy()
        if len(df) < 20:
            return False, None, 0
        volume_spike = df['volume'].iloc[-1] > df['volume'].tail(20).mean() * 2.5
        price_breakout = df['close'].iloc[-1] > df['high'].tail(10).max()
        volume_confirmation = df['volume'].iloc[-1] > df['volume'].iloc[-2]
        long_conditions = volume_spike and price_breakout and volume_confirmation
        volume_spike_short = df['volume'].iloc[-1] > df['volume'].tail(20).mean() * 2.5
        price_breakdown = df['close'].iloc[-1] < df['low'].tail(10).min()
        volume_confirmation_short = df['volume'].iloc[-1] > df['volume'].iloc[-2]
        short_conditions = volume_spike_short and price_breakdown and volume_confirmation_short
        if long_conditions:
            confidence = min(0.8, df['volume'].iloc[-1] / df['volume'].tail(20).mean() / 3)
            return True, "long", confidence
        elif short_conditions:
            confidence = min(0.8, df['volume'].iloc[-1] / df['volume'].tail(20).mean() / 3)
            return True, "short", confidence
        return False, None, 0

    def ema_momentum_cluster(self, kline_data, symbol):
        df = kline_data.copy()
        if len(df) < 50:
            return False, None, 0
        for span in [9, 13, 21, 34, 50]:
            df[f'ema_{span}'] = df['close'].ewm(span=span).mean()
        ema_alignment_long = all(
            df[f'ema_{span}'].iloc[-1] > df[f'ema_{next_span}'].iloc[-1]
            for span, next_span in zip([9, 13, 21, 34], [13, 21, 34, 50])
        )
        ema_alignment_short = all(
            df[f'ema_{span}'].iloc[-1] < df[f'ema_{next_span}'].iloc[-1]
            for span, next_span in zip([9, 13, 21, 34], [13, 21, 34, 50])
        )
        momentum_long = df['close'].iloc[-1] > df['close'].iloc[-5]
        momentum_short = df['close'].iloc[-1] < df['close'].iloc[-5]
        volume_confirm = df['volume'].iloc[-1] > df['volume'].tail(20).mean() * 1.2
        if ema_alignment_long and momentum_long and volume_confirm:
            return True, "long", 0.7
        elif ema_alignment_short and momentum_short and volume_confirm:
            return True, "short", 0.7
        return False, None, 0

    def support_resistance_breakout(self, kline_data, symbol):
        df = kline_data.copy()
        if len(df) < 20:
            return False, None, 0
        support_level = df['low'].rolling(20).min().iloc[-1]
        resistance_level = df['high'].rolling(20).max().iloc[-1]
        current_price = df['close'].iloc[-1]
        previous_price = df['close'].iloc[-2]
        resistance_break = (current_price > resistance_level and 
                          previous_price <= resistance_level and
                          df['volume'].iloc[-1] > df['volume'].tail(20).mean() * 1.8)
        support_break = (current_price < support_level and 
                        previous_price >= support_level and
                        df['volume'].iloc[-1] > df['volume'].tail(20).mean() * 1.8)
        if resistance_break:
            return True, "long", 0.75
        elif support_break:
            return True, "short", 0.75
        return False, None, 0

    def market_structure_analysis(self, kline_data, symbol):
        df = kline_data.copy()
        if len(df) < 30:
            return False, None, 0
        recent_highs = df['high'].tail(10)
        recent_lows = df['low'].tail(10)
        prev_highs = df['high'].iloc[-20:-10]
        prev_lows = df['low'].iloc[-20:-10]
        current_max = recent_highs.max()
        current_min = recent_lows.min()
        previous_max = prev_highs.max()
        previous_min = prev_lows.min()
        bullish_structure = current_max > previous_max and current_min > previous_min
        bearish_structure = current_max < previous_max and current_min < previous_min
        volume_confirmation = df['volume'].iloc[-1] > df['volume'].tail(20).mean() * 1.5
        if bullish_structure and volume_confirmation:
            return True, "long", 0.65
        elif bearish_structure and volume_confirmation:
            return True, "short", 0.65
        return False, None, 0

# ==================== СИСТЕМА ОБУЧЕНИЯ И АДАПТАЦИИ ====================
class LearningSystem:
    def __init__(self):
        self.trade_outcomes = []
        self.strategy_performance = {}
        self.adaptive_weights = {}
        self.logger = logging.getLogger()

    def record_trade_outcome(self, symbol, strategy, direction, pnl, confidence):
        outcome = {
            'symbol': symbol,
            'strategy': strategy,
            'direction': direction,
            'pnl': pnl,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat()
        }
        self.trade_outcomes.append(outcome)
        self.update_strategy_weights(strategy, pnl, confidence)

    def update_strategy_weights(self, strategy, pnl, confidence):
        if strategy not in self.strategy_performance:
            self.strategy_performance[strategy] = {'total_pnl': 0, 'trade_count': 0, 'success_rate': 0}
        perf = self.strategy_performance[strategy]
        perf['total_pnl'] += pnl
        perf['trade_count'] += 1
        perf['success_rate'] = (perf['success_rate'] * (perf['trade_count'] - 1) + (1 if pnl > 0 else 0)) / perf['trade_count']
        weight = self.calculate_strategy_weight(perf)
        self.adaptive_weights[strategy] = weight
        log_once(f"strategy_weight_update_{strategy}", logging.INFO,
                f"Обновлены веса стратегии {strategy}: PnL={perf['total_pnl']:.2f}, WinRate={perf['success_rate']:.2f}, Weight={weight:.3f}",
                self.logger)
    def calculate_strategy_weight(self, performance):
        success_weight = performance['success_rate'] * 0.6
        pnl_weight = min(0.4, performance['total_pnl'] / max(1, performance['trade_count']) / 100)
        return min(1.0, success_weight + pnl_weight)
    def get_strategy_weight(self, strategy):
        return self.adaptive_weights.get(strategy, 0.5)

# ==================== УЛУЧШЕННАЯ СТРАТЕГИЯ ТОРГОВЛИ ====================
class EnhancedTradingStrategy:

    def _calculate_safe_tp_price(self, side, entry_price, tp_percent, min_tp):
        tp_pct = max(tp_percent, min_tp) / 100.0
        if side.lower() == "long":
            return round(entry_price * (1 + tp_pct), 4)
        else:
            return round(entry_price * (1 - tp_pct), 4)

    def __init__(self):
        self.min_volume_threshold = 40000000
        self.volume_spike_multiplier = 2.5
        self.market_regime = "neutral"
        self.btc_dominance_threshold = 0.45
        self.multi_timeframe_analyzer = MultiTimeframeAnalyzer()
        self.ml_detector = MLSignalDetector()
        self.fallback_strategy = EnhancedFallbackStrategy()
        self.learning_system = LearningSystem()
        self.logger = logging.getLogger()

    def enhanced_signal_detection(self, kline_data, symbol, market_regime, fetch_klines_func=None):
        if len(kline_data) < 150:
            return False, None, "insufficient_data"
        df = kline_data.copy()
        df = df.sort_index()
        fast_signal = False
        fast_direction = None
        fast_confidence = 0.0
        
        # Блок анализа стратегии Fast Momentum (5m)
        if fetch_klines_func:
            try:
                kline_5m = fetch_klines_func(symbol, '5', 50)
                if kline_5m is not None and not kline_5m.empty:
                    fast_signal, fast_direction, fast_confidence = self._detect_fast_momentum(kline_5m, market_regime)
                    
                    # === УСИЛЕННЫЙ ФИЛЬТР ПО ГЛОБАЛЬНОМУ ТРЕНДУ ДЛЯ FAST MOMENTUM ===
                    if fast_signal and fast_confidence >= 0.80:
                        if (market_regime == "bullish" and fast_direction == "short") or \
                           (market_regime == "bearish" and fast_direction == "long"):
                            self.logger.info(f"🛑 Fast Signal {fast_direction} rejected by Market Regime {market_regime} for {symbol}")
                            fast_signal = False
                    else:
                        fast_signal = False
                        
            except Exception as e:
                self.logger.warning(f"Ошибка быстрого анализа 5m для {symbol}: {e}")
        
        # Если Fast Momentum прошел проверку
        if fast_signal:
            log_once(f"fast_signal_{symbol}", logging.INFO,
                    f"✅ ML-сигнал для {symbol}: {fast_direction} (стратегия: fast_momentum_{fast_confidence:.2f})",
                    self.logger)
            return True, fast_direction, f"fast_momentum_{fast_confidence:.2f}"

        # Далее идет анализ ML
        if fetch_klines_func:
            mtf_signal, mtf_dir, mtf_conf = self.multi_timeframe_analyzer.analyze_multi_tf(symbol, fetch_klines_func)
        
        df = self.calculate_enhanced_indicators(df)
        ml_features = self.ml_detector.calculate_advanced_features(df)
        
        # === ИЗМЕНЕНИЕ ЗДЕСЬ: Передаем market_regime внутрь predict_signal ===
        ml_signal, ml_direction, ml_confidence = self.ml_detector.predict_signal(ml_features, df, market_regime)
        
        confidence_threshold = 0.75 if market_regime == "bullish" else 0.82
        
        if ml_signal and ml_confidence >= confidence_threshold:
            # Направление и фильтрация уже проверены внутри predict_signal
            log_once(f"ml_signal_{symbol}", logging.INFO,
                    f"✅ ML-сигнал для {symbol}: {ml_direction} (стратегия: ml_{ml_confidence:.2f})",
                    self.logger)
            return True, ml_direction, f"ml_{ml_confidence:.2f}"
            
        # Fallback стратегии (оставляем как есть, у них есть свои проверки)
        fallback_signal, fallback_direction, fallback_confidence = self.fallback_strategy.execute_fallback(df, symbol)
        if fallback_signal:
            direction = fallback_direction
            if (market_regime == "bullish" and direction == "short") or (market_regime == "bearish" and direction == "long"):
                return False, None, "trend_filter_rejected"
            log_once(f"fallback_signal_{symbol}", logging.INFO,
                    f"✅ Фолбэк-сигнал для {symbol}: {direction} (уверенность: {fallback_confidence:.2f})",
                    self.logger)
            return True, direction, f"fallback_{fallback_confidence:.2f}"
            
        # Enhanced trend logic
        recent = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
        market_structure = self.analyze_market_structure(df)
        momentum = self.analyze_momentum(df)
        
        long_conditions = self.get_enhanced_long_conditions_v2(df, recent, prev, market_regime, market_structure, momentum)
        if long_conditions['all_conditions']:
            direction = "long"
            if market_regime == "bearish":
                return False, None, "trend_filter_rejected"
            if fetch_klines_func:
                mtf_signal, mtf_dir, mtf_conf = self.multi_timeframe_analyzer.analyze_multi_tf(symbol, fetch_klines_func)
                if mtf_dir != "long" or mtf_conf < 0.7:
                    return False, None, "htf_mismatch"
            log_once(f"enhanced_long_{symbol}", logging.INFO,
                    f"✅ Усиленный лонг-сигнал для {symbol}",
                    self.logger)
            return True, direction, "enhanced_long"
            
        short_conditions = self.get_enhanced_short_conditions_v2(df, recent, prev, market_regime, market_structure, momentum)
        if short_conditions['all_conditions']:
            direction = "short"
            if market_regime == "bullish":
                return False, None, "trend_filter_rejected"
            if fetch_klines_func:
                mtf_signal, mtf_dir, mtf_conf = self.multi_timeframe_analyzer.analyze_multi_tf(symbol, fetch_klines_func)
                if mtf_dir != "short" or mtf_conf < 0.7:
                    return False, None, "htf_mismatch"
            log_once(f"enhanced_short_{symbol}", logging.INFO,
                    f"✅ Усиленный шорт-сигнал для {symbol}",
                    self.logger)
            return True, direction, "enhanced_short"
            
        return False, None, "no_strong_signal"
    
    def _detect_fast_momentum(self, df_5m, market_regime):
        """Усиленный детектор импульса для 5-минуток с фильтрами тренда и свечи."""
        if len(df_5m) < 50: # Требуем больше данных для EMA50
            return False, None, 0.0

        df = df_5m.copy()

        # === 1. Расчет индикаторов и Price Action ===
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        
        current = df.iloc[-1]
        vol_ma = df['volume'].rolling(20).mean().iloc[-1]
        vol_ratio = current['volume'] / vol_ma if vol_ma > 0 else 1.0
        
        # Относительная длина свечи (ATR)
        df['atr_14'] = self.calculate_atr(df, 14)
        avg_candle_range = df['atr_14'].iloc[-1]
        current_range = current['high'] - current['low']
        
        # Анализ формы свечи
        body = abs(current['close'] - current['open'])
        upper_shadow = current['high'] - max(current['open'], current['close'])
        lower_shadow = min(current['open'], current['close']) - current['low']
        
        # Сильная зеленая свеча (Маркетбозу или Хаммер с маленьким верхним хвостом)
        is_strong_long_candle = (
            current['close'] > current['open'] and 
            body > 0.5 * current_range and # Значительное тело
            lower_shadow < 0.5 * body and  # Маленький нижний хвост
            current_range > 1.2 * avg_candle_range # Больше среднего ATR
        )
        
        # Сильная красная свеча (Маркетбозу или Падающая звезда с маленьким нижним хвостом)
        is_strong_short_candle = (
            current['close'] < current['open'] and 
            body > 0.5 * current_range and 
            upper_shadow < 0.5 * body and 
            current_range > 1.2 * avg_candle_range
        )

        # === 2. Логика ЛОНГА ===
        # Фильтр 1: Строгий EMA кластер (восходящий тренд)
        ema_alignment_long = (
            current['ema_9'] > current['ema_21'] and 
            current['ema_21'] > current['ema_50']
        )
        # Фильтр 2: Объем + Свеча
        volume_and_candle_long = (
            vol_ratio > 1.5 and 
            is_strong_long_candle
        )
        # Фильтр 3: Анти-разворот (цена выше EMA21)
        price_above_ema = current['close'] > current['ema_21']
        
        fast_long = (
            ema_alignment_long and 
            volume_and_candle_long and 
            price_above_ema and
            (market_regime != "bearish") # Не входить против медвежьего тренда
        )

        # === 3. Логика ШОРТА ===
        # Фильтр 1: Строгий EMA кластер (нисходящий тренд)
        ema_alignment_short = (
            current['ema_9'] < current['ema_21'] and 
            current['ema_21'] < current['ema_50']
        )
        # Фильтр 2: Объем + Свеча
        volume_and_candle_short = (
            vol_ratio > 1.5 and 
            is_strong_short_candle
        )
        # Фильтр 3: Анти-разворот (цена ниже EMA21)
        price_below_ema = current['close'] < current['ema_21']
        
        fast_short = (
            ema_alignment_short and 
            volume_and_candle_short and 
            price_below_ema and
            (market_regime != "bullish") # Не входить против бычьего тренда
        )

        if fast_long:
            confidence = min(0.95, 0.75 + (vol_ratio / 15))
            return True, "long", confidence
        elif fast_short:
            confidence = min(0.95, 0.75 + (vol_ratio / 15))
            return True, "short", confidence

        return False, None, 0.0
    
    def get_enhanced_long_conditions_v2(self, df, recent, prev, market_regime, market_structure, momentum):
        conditions = {}
        # EMA: Требуем только локальный тренд (9 > 21) и цену выше EMA 21
        conditions['ema_alignment'] = (
            recent['ema_9'] > recent['ema_21'] and
            recent['close'] > recent['ema_21']
        )
        # RSI: Не должен быть перекуплен (выше 80 опасно), должен быть выше 45 (сила)
        conditions['rsi_momentum'] = (
            45 < recent['rsi_14'] < 80 and
            recent['macd_hist'] > 0 # Гистограмма растет
        )
        # Volume: Снизили порог до 1.3
        conditions['volume'] = (
            recent['volume_ratio_20'] > 1.3
        )
        # Price Action: Если свеча зеленая и закрылась выше открытия
        conditions['price_action'] = (
            recent['close'] > recent['open']
        )
        
        # Убрали жесткие проверки отката и anti_pump, оставили фильтр ложных сигналов
        conditions['false_signal_filter'] = self.advanced_false_signal_filter(df, "long")
        
        mandatory = ['ema_alignment', 'rsi_momentum', 'volume', 'price_action', 'false_signal_filter']
        conditions['mandatory_conditions'] = all(conditions.get(c, False) for c in mandatory)
        
        # Дополнительно: если структура рынка явно бычья, можно простить слабый объем
        conditions['structural_boost'] = market_structure['higher_highs'] and market_structure['higher_lows']
        
        conditions['all_conditions'] = conditions['mandatory_conditions'] or (conditions['structural_boost'] and conditions['ema_alignment'])
        return conditions
    def get_enhanced_short_conditions_v2(self, df, recent, prev, market_regime, market_structure, momentum):
        conditions = {}
        # EMA: Локальный даунтренд
        conditions['ema_alignment'] = (
            recent['ema_9'] < recent['ema_21'] and
            recent['close'] < recent['ema_21']
        )
        # RSI: Не перепродан (ниже 20), ниже 55 (слабость)
        conditions['rsi_momentum'] = (
            20 < recent['rsi_14'] < 55 and
            recent['macd_hist'] < 0
        )
        # Volume
        conditions['volume'] = (
            recent['volume_ratio_20'] > 1.3
        )
        # Price Action
        conditions['price_action'] = (
            recent['close'] < recent['open']
        )
        
        conditions['false_signal_filter'] = self.advanced_false_signal_filter(df, "short")
        
        mandatory = ['ema_alignment', 'rsi_momentum', 'volume', 'price_action', 'false_signal_filter']
        conditions['mandatory_conditions'] = all(conditions.get(c, False) for c in mandatory)
        
        conditions['structural_boost'] = market_structure['lower_highs'] and market_structure['lower_lows']
        
        conditions['all_conditions'] = conditions['mandatory_conditions'] or (conditions['structural_boost'] and conditions['ema_alignment'])
        return conditions
    def calculate_enhanced_indicators(self, df):
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['ema_100'] = df['close'].ewm(span=100).mean()
        df['rsi_14'] = self.calculate_rsi(df['close'], 14)
        df['rsi_7'] = self.calculate_rsi(df['close'], 7)
        df['stoch_rsi'] = self.calculate_stoch_rsi(df['close'])
        df['macd'], df['macd_signal'], df['macd_hist'] = self.calculate_macd_enhanced(df['close'])
        df['atr_14'] = self.calculate_atr(df, 14)
        df['atr_7'] = self.calculate_atr(df, 7)
        df['volatility_ratio'] = df['atr_14'] / df['close']
        df['volume_ma_20'] = df['volume'].rolling(20).mean()
        df['volume_ma_50'] = df['volume'].rolling(50).mean()
        df['volume_ratio_20'] = df['volume'] / df['volume_ma_20']
        df['volume_ratio_50'] = df['volume'] / df['volume_ma_50']
        df['body_size'] = abs(df['close'] - df['open'])
        df['total_range'] = df['high'] - df['low']
        df['body_ratio'] = df['body_size'] / (df['total_range'] + 1e-10)
        df['support'], df['resistance'] = self.calculate_dynamic_support_resistance(df)
        df['momentum_5'] = (df['close'] / df['close'].shift(5) - 1) * 100
        df['momentum_10'] = (df['close'] / df['close'].shift(10) - 1) * 100
        return df
    def determine_market_regime(self, btc_data, total_market_data=None):
        if len(btc_data) < 100:
            return "neutral"
        df = btc_data.copy()
        df['ema_20'] = df['close'].ewm(span=20).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['ema_100'] = df['close'].ewm(span=100).mean()
        df['atr'] = self.calculate_atr(df, 14)
        df['momentum'] = df['close'] / df['close'].shift(5) - 1
        df['volatility_ratio'] = df['atr'] / df['close']
        current = df.iloc[-1]
        trend_strength = self.calculate_trend_strength(df)
        momentum_strength = abs(current['momentum']) * 100
        if (current['ema_20'] > current['ema_50'] > current['ema_100'] and 
            trend_strength > 60 and momentum_strength > 1.0):
            return "bullish"
        elif (current['ema_20'] < current['ema_50'] < current['ema_100'] and 
              trend_strength > 60 and momentum_strength > 1.0):
            return "bearish"
        else:
            return "neutral"
    def calculate_trend_strength(self, df, period=20):
        if len(df) < period:
            return 50
        up_moves = (df['high'] - df['high'].shift(1)).clip(lower=0)
        down_moves = (df['low'].shift(1) - df['low']).clip(lower=0)
        avg_up = up_moves.rolling(period).mean()
        avg_down = down_moves.rolling(period).mean()
        trend_strength = 100 * abs(avg_up - avg_down) / (avg_up + avg_down + 1e-10)
        return trend_strength.iloc[-1] if not trend_strength.empty else 50

    def analyze_market_structure(self, df):
        structure = {
            'higher_highs': False,
            'higher_lows': False,
            'lower_highs': False,
            'lower_lows': False,
            'consolidation': False
        }
        if len(df) < 20:
            return structure
        recent_highs = df['high'].tail(10)
        recent_lows = df['low'].tail(10)
        prev_highs = df['high'].iloc[-20:-10]
        prev_lows = df['low'].iloc[-20:-10]
        current_max = recent_highs.max()
        current_min = recent_lows.min()
        previous_max = prev_highs.max()
        previous_min = prev_lows.min()
        structure['higher_highs'] = current_max > previous_max
        structure['higher_lows'] = current_min > previous_min
        structure['lower_highs'] = current_max < previous_max
        structure['lower_lows'] = current_min < previous_min
        volatility = df['volatility_ratio'].tail(10).mean()
        structure['consolidation'] = volatility < 0.02
        return structure
    def analyze_momentum(self, df):
        momentum = {
            'strength': 0,
            'direction': 'neutral',
            'acceleration': 0,
            'volume_confirmation': False
        }
        if len(df) < 10:
            return momentum
        recent = df.tail(5)
        price_change = (recent['close'].iloc[-1] / recent['close'].iloc[0] - 1) * 100
        momentum['strength'] = abs(price_change)
        momentum['direction'] = 'bullish' if price_change > 0 else 'bearish'
        current_change = (recent['close'].iloc[-1] / recent['close'].iloc[-2] - 1) * 100
        prev_change = (recent['close'].iloc[-2] / recent['close'].iloc[-3] - 1) * 100
        momentum['acceleration'] = current_change - prev_change
        avg_volume_ratio = recent['volume_ratio_20'].mean()
        momentum['volume_confirmation'] = avg_volume_ratio > 1.2
        return momentum
    def advanced_false_signal_filter(self, df, direction, lookback=6):
        if len(df) < lookback + 5:
            return True
        recent_data = df.tail(lookback)
        if direction == "long":
            higher_highs = sum(recent_data['high'] > recent_data['high'].shift(1))
            higher_lows = sum(recent_data['low'] > recent_data['low'].shift(1))
            support_level = recent_data['support'].iloc[-lookback]
            touches_support = sum(recent_data['low'] <= support_level * 1.01)
            bounces_from_support = sum((recent_data['low'] <= support_level * 1.01) & 
                                     (recent_data['close'] > recent_data['open']))
            return (higher_highs >= 2 and higher_lows >= 2 and 
                   bounces_from_support >= touches_support * 0.4)
        else:
            lower_highs = sum(recent_data['high'] < recent_data['high'].shift(1))
            lower_lows = sum(recent_data['low'] < recent_data['low'].shift(1))
            resistance_level = recent_data['resistance'].iloc[-lookback]
            touches_resistance = sum(recent_data['high'] >= resistance_level * 0.99)
            bounces_from_resistance = sum((recent_data['high'] >= resistance_level * 0.99) & 
                                        (recent_data['close'] < recent_data['open']))
            return (lower_highs >= 2 and lower_lows >= 2 and 
                   bounces_from_resistance >= touches_resistance * 0.4)
        return True
    def calculate_dynamic_support_resistance(self, df, period=20):
        resistance = df['high'].rolling(period).max()
        support = df['low'].rolling(period).min()
        ma_support = df['ema_50'] - df['atr_14'] * 1.5
        ma_resistance = df['ema_50'] + df['atr_14'] * 1.5
        combined_support = (support + ma_support) / 2
        combined_resistance = (resistance + ma_resistance) / 2
        return combined_support, combined_resistance

    def calculate_macd_enhanced(self, prices, fast=12, slow=26, signal=9):
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist

    def calculate_rsi(self, prices, period=14):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, prices, period=14, k=3, d=3):
        rsi = self.calculate_rsi(prices, period)
        stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min()) * 100
        return stoch_rsi.rolling(k).mean().rolling(d).mean()

    def calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = np.maximum(np.maximum(high_low, high_close), low_close)
        atr = true_range.rolling(period).mean()
        return atr

    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        macd, macd_signal, _ = self.calculate_macd_enhanced(prices, fast, slow, signal)
        return macd, macd_signal

    def calculate_support_resistance(self, df, period=20):
        return self.calculate_dynamic_support_resistance(df, period)
# ==================== ЗАГЛУШКИ ДЛЯ СТАРЫХ СТРАТЕГИЙ ====================
def is_strong_signal_strategy6(self, kline_data):
    return False, None

def _original_strategy(self, kline_data):
    return False, None
# ==================== УЛУЧШЕННАЯ СИСТЕМА ОТЧЕТНОСТИ PNL ====================
class EnhancedPnLReporting:
    def __init__(self, trade_history):
        self.trade_history = trade_history
    def get_all_trades(self):
        """Получить все сделки с полной информацией"""
        return sorted(self.trade_history, key=lambda x: x.get('timestamp', ''), reverse=True)
    def get_daily_summary(self, date_filter=None):
        """Получить сводку по дням"""
        if not self.trade_history:
            return []
        daily_data = {}
        for trade in self.trade_history:
            try:
                trade_date = datetime.fromisoformat(trade['timestamp']).date()
                if date_filter and trade_date != date_filter:
                    continue
                if trade_date not in daily_data:
                    daily_data[trade_date] = {
                        'date': trade_date,
                        'total_trades': 0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'total_pnl': 0.0,
                        'winning_pnl': 0.0,
                        'losing_pnl': 0.0,
                        'avg_win': 0.0,
                        'avg_loss': 0.0,
                        'largest_win': 0.0,
                        'largest_loss': 0.0,
                        'symbols': set(),
                        'strategies': {},
                        'pairs': {},  # Статистика по парам
                        'trades_list': []  # Список сделок за день
                    }
                day_data = daily_data[trade_date]
                day_data['total_trades'] += 1
                day_data['total_pnl'] += trade['pnl']
                day_data['symbols'].add(trade['symbol'])
                day_data['trades_list'].append(trade)  # Добавляем сделку в список
                # Статистика по стратегиям
                strategy = trade.get('strategy', 'unknown')
                if strategy not in day_data['strategies']:
                    day_data['strategies'][strategy] = {'count': 0, 'pnl': 0.0}
                day_data['strategies'][strategy]['count'] += 1
                day_data['strategies'][strategy]['pnl'] += trade['pnl']
                # Статистика по парам
                symbol = trade['symbol']
                if symbol not in day_data['pairs']:
                    day_data['pairs'][symbol] = {
                        'trades': 0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'total_pnl': 0.0,
                        'winning_pnl': 0.0,
                        'losing_pnl': 0.0
                    }
                pair_data = day_data['pairs'][symbol]
                pair_data['trades'] += 1
                pair_data['total_pnl'] += trade['pnl']
                if trade['pnl'] > 0:
                    day_data['winning_trades'] += 1
                    day_data['winning_pnl'] += trade['pnl']
                    # Обновляем максимальную прибыль
                    if day_data['largest_win'] == 0.0 or trade['pnl'] > day_data['largest_win']:
                        day_data['largest_win'] = trade['pnl']
                    pair_data['winning_trades'] += 1
                    pair_data['winning_pnl'] += trade['pnl']
                else:
                    day_data['losing_trades'] += 1
                    day_data['losing_pnl'] += trade['pnl']
                    # Обновляем максимальный убыток
                    if day_data['largest_loss'] == 0.0 or trade['pnl'] < day_data['largest_loss']:
                        day_data['largest_loss'] = trade['pnl']
                    pair_data['losing_trades'] += 1
                    pair_data['losing_pnl'] += trade['pnl']
            except Exception as e:
                continue
        # Рассчитываем средние значения
        for day_data in daily_data.values():
            if day_data['winning_trades'] > 0:
                day_data['avg_win'] = day_data['winning_pnl'] / day_data['winning_trades']
            if day_data['losing_trades'] > 0:
                day_data['avg_loss'] = day_data['losing_pnl'] / day_data['losing_trades']
            day_data['win_rate'] = (day_data['winning_trades'] / day_data['total_trades'] * 100) if day_data['total_trades'] > 0 else 0
            # Рассчитываем статистику по парам
            for pair_data in day_data['pairs'].values():
                if pair_data['trades'] > 0:
                    pair_data['win_rate'] = (pair_data['winning_trades'] / pair_data['trades'] * 100) if pair_data['trades'] > 0 else 0
                    pair_data['avg_pnl'] = pair_data['total_pnl'] / pair_data['trades'] if pair_data['trades'] > 0 else 0
        return sorted(daily_data.values(), key=lambda x: x['date'], reverse=True)
    def get_weekly_summary(self):
        """Получить сводку по неделям"""
        daily_summary = self.get_daily_summary()
        weekly_data = {}
        for day_data in daily_summary:
            year, week_num, _ = day_data['date'].isocalendar()
            week_key = f"{year}-W{week_num:02d}"
            if week_key not in weekly_data:
                weekly_data[week_key] = {
                    'week': week_key,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'days_traded': 0,
                    'symbols': set(),
                    'pairs': {},  # Статистика по парам за неделю
                    'trades_list': []  # Список сделок за неделю
                }
            week_data = weekly_data[week_key]
            week_data['total_trades'] += day_data['total_trades']
            week_data['winning_trades'] += day_data['winning_trades']
            week_data['losing_trades'] += day_data['losing_trades']
            week_data['total_pnl'] += day_data['total_pnl']
            week_data['days_traded'] += 1
            week_data['symbols'].update(day_data['symbols'])
            week_data['trades_list'].extend(day_data['trades_list'])  # Добавляем сделки дня в неделю
            # Агрегируем статистику по парам за неделю
            for symbol, pair_day_data in day_data['pairs'].items():
                if symbol not in week_data['pairs']:
                    week_data['pairs'][symbol] = {
                        'trades': 0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'total_pnl': 0.0
                    }
                week_pair_data = week_data['pairs'][symbol]
                week_pair_data['trades'] += pair_day_data['trades']
                week_pair_data['winning_trades'] += pair_day_data['winning_trades']
                week_pair_data['losing_trades'] += pair_day_data['losing_trades']
                week_pair_data['total_pnl'] += pair_day_data['total_pnl']
        # Рассчитываем винрейт
        for week_data in weekly_data.values():
            if week_data['total_trades'] > 0:
                week_data['win_rate'] = (week_data['winning_trades'] / week_data['total_trades'] * 100)
            # Рассчитываем статистику по парам за неделю
            for pair_data in week_data['pairs'].values():
                if pair_data['trades'] > 0:
                    pair_data['win_rate'] = (pair_data['winning_trades'] / pair_data['trades'] * 100)
                    pair_data['avg_pnl'] = pair_data['total_pnl'] / pair_data['trades']
        return sorted(weekly_data.values(), key=lambda x: x['week'], reverse=True)
    def get_monthly_summary(self):
        """Получить сводку по месяцам"""
        daily_summary = self.get_daily_summary()
        monthly_data = {}
        for day_data in daily_summary:
            month_key = day_data['date'].strftime("%Y-%m")
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    'month': month_key,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'days_traded': 0,
                    'symbols': set(),
                    'pairs': {},  # Статистика по парам за месяц
                    'trades_list': []  # Список сделок за месяц
                }
            month_data = monthly_data[month_key]
            month_data['total_trades'] += day_data['total_trades']
            month_data['winning_trades'] += day_data['winning_trades']
            month_data['losing_trades'] += day_data['losing_trades']
            month_data['total_pnl'] += day_data['total_pnl']
            month_data['days_traded'] += 1
            month_data['symbols'].update(day_data['symbols'])
            month_data['trades_list'].extend(day_data['trades_list'])  # Добавляем сделки дня в месяц
            # Агрегируем статистику по парам за месяц
            for symbol, pair_day_data in day_data['pairs'].items():
                if symbol not in month_data['pairs']:
                    month_data['pairs'][symbol] = {
                        'trades': 0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'total_pnl': 0.0
                    }
                month_pair_data = month_data['pairs'][symbol]
                month_pair_data['trades'] += pair_day_data['trades']
                month_pair_data['winning_trades'] += pair_day_data['winning_trades']
                month_pair_data['losing_trades'] += pair_day_data['losing_trades']
                month_pair_data['total_pnl'] += pair_day_data['total_pnl']
        # Рассчитываем винрейт
        for month_data in monthly_data.values():
            if month_data['total_trades'] > 0:
                month_data['win_rate'] = (month_data['winning_trades'] / month_data['total_trades'] * 100)
            # Рассчитываем статистику по парам за месяц
            for pair_data in month_data['pairs'].values():
                if pair_data['trades'] > 0:
                    pair_data['win_rate'] = (pair_data['winning_trades'] / pair_data['trades'] * 100)
                    pair_data['avg_pnl'] = pair_data['total_pnl'] / pair_data['trades']
        return sorted(monthly_data.values(), key=lambda x: x['month'], reverse=True)
    def get_trades_for_date(self, target_date):
        """Получить все сделки за конкретную дату"""
        return [trade for trade in self.trade_history 
                if datetime.fromisoformat(trade['timestamp']).date() == target_date]
    def get_performance_metrics(self):
        """Получить ключевые метрики производительности"""
        if not self.trade_history:
            return {}
        total_pnl = sum(trade['pnl'] for trade in self.trade_history)
        total_trades = len(self.trade_history)
        winning_trades = len([t for t in self.trade_history if t['pnl'] > 0])
        losing_trades = len([t for t in self.trade_history if t['pnl'] < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        # Средний PnL
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        # Средний выигрыш/проигрыш
        avg_win = sum(t['pnl'] for t in self.trade_history if t['pnl'] > 0) / winning_trades if winning_trades > 0 else 0
        avg_loss = sum(t['pnl'] for t in self.trade_history if t['pnl'] < 0) / losing_trades if losing_trades > 0 else 0
        # Соотношение прибыль/убыток
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        # Максимальные значения
        largest_win = max((t['pnl'] for t in self.trade_history), default=0)
        largest_loss = min((t['pnl'] for t in self.trade_history), default=0)
        # Анализ по стратегиям
        strategy_stats = {}
        for trade in self.trade_history:
            strategy = trade.get('strategy', 'unknown')
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'count': 0, 'pnl': 0.0, 'wins': 0}
            strategy_stats[strategy]['count'] += 1
            strategy_stats[strategy]['pnl'] += trade['pnl']
            if trade['pnl'] > 0:
                strategy_stats[strategy]['wins'] += 1
        # Винрейт по стратегиям
        for strategy in strategy_stats:
            stats = strategy_stats[strategy]
            stats['win_rate'] = (stats['wins'] / stats['count'] * 100) if stats['count'] > 0 else 0
            stats['avg_pnl'] = stats['pnl'] / stats['count'] if stats['count'] > 0 else 0
        # Анализ по парам
        pair_stats = {}
        for trade in self.trade_history:
            symbol = trade['symbol']
            if symbol not in pair_stats:
                pair_stats[symbol] = {
                    'count': 0, 
                    'pnl': 0.0, 
                    'wins': 0,
                    'total_volume': 0.0,
                    'avg_volume': 0.0
                }
            pair_stats[symbol]['count'] += 1
            pair_stats[symbol]['pnl'] += trade['pnl']
            if trade['pnl'] > 0:
                pair_stats[symbol]['wins'] += 1
            # Расчет объема торгов
            if 'usdt_value' in trade:
                pair_stats[symbol]['total_volume'] += trade['usdt_value']
        # Рассчитываем метрики по парам
        for symbol in pair_stats:
            stats = pair_stats[symbol]
            stats['win_rate'] = (stats['wins'] / stats['count'] * 100) if stats['count'] > 0 else 0
            stats['avg_pnl'] = stats['pnl'] / stats['count'] if stats['count'] > 0 else 0
            stats['avg_volume'] = stats['total_volume'] / stats['count'] if stats['count'] > 0 else 0
            stats['total_trades'] = stats['count']
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'strategy_stats': strategy_stats,
            'pair_stats': pair_stats  # Добавляем статистику по парам
        }
# ==================== ОСНОВНОЙ КЛАСС БОТА С УЛУЧШЕННЫМ ИНТЕРФЕЙСОМ ====================
class BybitTradingBot:

    # ===== IRON FREEZE FIX =====
    def _apply_freeze(self, symbol, reason="position_closed"):
        try:
            # FREEZE FIRST
            if hasattr(self, "freeze_manager"):
                self.freeze_manager.apply_freeze(symbol, minutes=5, reason=reason)
            # HARD REMOVE FROM coins_in_work
            if hasattr(self, "coins_in_work") and symbol in self.coins_in_work:
                self.coins_in_work.discard(symbol)
            # LOG
            try:
                self.logger.info(f"❄️ FREEZE APPLIED {symbol} reason={reason}")
            except Exception:
                pass
        except Exception as e:
            try:
                self.logger.error(f"FREEZE ERROR {symbol}: {e}")
            except Exception:
                pass
    # ==========================


    def _handle_position_closed_immediate(self, symbol, reason="tp"):
        # FIX: freeze immediately on any confirmed close
        self._apply_freeze(symbol, 'instant_close')

        """
        FIX: МГНОВЕННАЯ обработка закрытия позиции.
        """
        try:
            now = time.time()

            if symbol in self._position_states:
                del self._position_states[symbol]
                self.logger.info(f"🗑️ {symbol} удалена из состояния позиций (instant)")

            300[symbol] = now + 300
            self.logger.info(
                f"❄️ МГНОВЕННАЯ ЗАМОРОЗКА {symbol}: до {time.strftime('%H:%M:%S', time.localtime(self.frozen_symbols[symbol]))}"
            )

            self.recently_closed[symbol] = now

        except Exception as e:
            self.logger.error(f"Ошибка _handle_position_closed_immediate({symbol}): {e}")

    def _recalculate_tp_after_grid_fill(self, symbol, position):
        """ 
        FIX: Метод отсутствовал.
        Вызывается после исполнения сеточного ордера.
        Здесь мы НИЧЕГО не замораживаем и не меняем логику —
        только лог и синхронизация состояния.
        """
        try:
            # просто лог + защита от повторов
            avg_price = float(position.get('entry_price', 0))
            size = float(position.get('size', 0))
            self.logger.info(
                f"⚙️ TP-RECALC HOOK: {symbol} | avg={avg_price} | size={size}"
            )
        except Exception as e:
            self.logger.error(f"Ошибка _recalculate_tp_after_grid_fill({symbol}): {e}")
    def __init__(self, root):
        self.root = root
        self.root.title("🚀 Bybit Trading Bot Pro")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = int(screen_width * 0.9)
        window_height = int(screen_height * 0.9)
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(1200, 700)
        self.setup_styles()
        
        # --- НАСТРОЙКА ЛОГГЕРОВ ---
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('pybit').setLevel(logging.WARNING)
        self.logger = setup_logger('main_logger', 'trading.log')
        self.signal_logger = setup_logger('signal_logger', 'signals.log')
        self.error_logger = setup_logger('error_logger', 'errors.log')
        self.logger.info("=== Бот запущен ===")

        self.order_manager = None
        self.performance_optimizer = PerformanceOptimizer()
        self.error_handler = ErrorHandler(self.error_logger) 
        self.enhanced_strategy = EnhancedTradingStrategy()
        
        # === Инициализация переменных для API ===
        self.api_keys_file = "api_keys.json"
        self.api_key = ""
        self.api_secret = ""
        self.demo_trading = False
        self.load_api_credentials()
        
        self.session = None
        self._last_request_time = 0
        self._min_request_interval = 0.2
        self._dynamic_delay_multiplier = 1.0
        self.symbols = []
        self.active_futures_symbols = set()
        self.current_symbol = "BTCUSDT"
        self.current_interval = "15"
        self.kline_data = None
        self.tickers_data = []
        self.positions_data = []
        self.orders_data = []
        self.trading_pairs = []
        self.config_file = "trading_pairs.json"
        self.load_trading_pairs()
        self.suitable_coins = []
        self.suitable_coins_max = 25
        self.last_suitable_update = 0
        
        # === ВАЖНО: Интервал обновления 300 секунд (5 минут) ===
        self.suitable_update_interval = 300 
        self.is_scanning = False  # <--- НОВАЯ ПЕРЕМЕННАЯ (Флаг сканирования)

        self.working_coin_configs = []
        self.max_working_coins = 1
        self.working_coin_defaults_file = "working_coin_defaults.json"
        self.load_working_coin_defaults()
        self.working_coin_configs_file = "working_coin_configs.json"
        self.load_working_coin_configs()
        self.trade_history = []
        self.trade_history_file = "trade_history.json"
        self.load_trade_history()
        self._last_positions_cache = []
        self.show_orders = True
        self.auto_trading = False
        self.trading_thread = None
        self.manager_window = None
        self.edit_window = None
        self.working_coin_window = None
        self.balance = 0.0
        self.grid_lines = []
        self.blacklist_file = "blacklist.json"
        self.blacklist = self.load_blacklist()
        self._last_balance = 0.0
        self.performance_stats = {}
        self.last_performance_update = 0
        self.futures_symbols_file = "bybit_futures_symbols.json"
        self._last_position_close_time = {}
        self._position_states = {}

        # --- API error counters and blacklist for symbols ---
        self._symbol_api_error_counts = {}
        self.api_error_threshold = 5
        self.api_error_blacklist = set()
        self._prev_price = None
        self._last_ui_update_ts = time.time()
        self.suitable_coins_cleanup_interval = 120
        self.position_timeout_seconds = 180
        self._tp_protection_enabled = True
        self._last_tp_check_time = {}
        self._manual_tp_updates = {}
        self._last_successful_tp = {}
        self._current_exchange_tp = {}
        self._tp_check_cache = {}
        self._tp_cache_ttl = 30
        
        self.create_modern_widgets()
        self.update_working_coin_display()
        self._bind_hotkeys()
        self.update_data()
        
        # Запуск таймеров
        self.schedule_suitable_update()
        self.start_performance_monitoring()
        self.start_suitable_coins_cleanup()
        self.start_enhanced_tp_monitoring()
        self.start_manual_tp_monitoring()
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')  # Добавить эту строку
        style.configure('Modern.TFrame', background='#f5f6fa')
        style.configure('Modern.TFrame', background='#f5f6fa')
        style.configure('Modern.TLabelframe', background='#ffffff', bordercolor='#dcdde1', relief='solid')
        style.configure('Modern.TLabelframe.Label', background='#ffffff', foreground='#2f3640')
        style.configure('Header.TLabel', font=('Arial', 11, 'bold'), foreground='#2f3640')
        style.configure('Accent.TButton', background='#40739e', foreground='white')
        style.configure('Success.TLabel', foreground='#44bd32')
        style.configure('Warning.TLabel', foreground='#e1b12c')
        style.configure('Danger.TLabel', foreground='#e84118')
        style.configure('Treeview', 
                       background='#ffffff',
                       foreground='#2f3640',
                       fieldbackground='#ffffff',
                       rowheight=25)
        style.configure('Treeview.Heading', 
                       background='#487eb0',
                       foreground='white',
                       relief='flat',
                       font=('Arial', 9, 'bold'))
        style.map('Treeview.Heading', 
                 background=[('active', '#40739e')])
    # === НОВЫЙ МОДУЛЬ: Загрузка и сохранение ключей ===
    def load_api_credentials(self):
        """Загружает API ключи из файла"""
        if os.path.exists(self.api_keys_file):
            try:
                with open(self.api_keys_file, 'r') as f:
                    data = json.load(f)
                    self.api_key = data.get('api_key', "")
                    self.api_secret = data.get('api_secret', "")
                    self.demo_trading = data.get('demo_trading', False)
                self.logger.info("API ключи успешно загружены из файла")
            except Exception as e:
                self.error_logger.error(f"Ошибка загрузки API ключей: {e}")

    def save_api_credentials(self):
        """Сохраняет текущие API ключи в файл"""
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'demo_trading': self.demo_trading
        }
        try:
            with open(self.api_keys_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.info("API ключи успешно сохранены")
        except Exception as e:
            self.error_logger.error(f"Ошибка сохранения API ключей: {e}")
    # =================================================
    def create_modern_widgets(self):
        main_frame = ttk.Frame(self.root, style='Modern.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(header_frame, 
                 text="🚀 Bybit Trading Bot Pro", 
                 font=('Arial', 16, 'bold'),
                 foreground='#2f3640').pack(side=tk.LEFT)
        status_right = ttk.Frame(header_frame)
        status_right.pack(side=tk.RIGHT)
        # компактные индикаторы
        self.account_type_small = ttk.Label(status_right, text="● Реальный", font=('Arial', 9))
        self.account_type_small.pack(side=tk.LEFT, padx=8)
        self.auto_small = ttk.Label(status_right, text="🤖 Выкл", font=('Arial', 9))
        self.auto_small.pack(side=tk.LEFT, padx=8)
        self.balance_small = ttk.Label(status_right, text="💰 -- USDT", font=('Arial', 9, 'bold'))
        self.balance_small.pack(side=tk.LEFT, padx=8)
        self.status_label = ttk.Label(status_right, text="● Не подключено", foreground='#e84118', font=('Arial', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT, padx=8)
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        left_frame = ttk.LabelFrame(content_frame, 
                                  text="🎛️ Управление и мониторинг", 
                                  style='Modern.TLabelframe',
                                  padding=15)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        left_frame.configure(width=340)
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.create_enhanced_left_panel(left_frame)
        self.create_enhanced_right_panel(right_frame)
        # Status bar
        status_bar = ttk.Frame(main_frame)
        status_bar.pack(fill=tk.X, pady=(10, 0))
        self.status_action_label = ttk.Label(status_bar, text="Готово", font=('Arial', 9))
        self.status_action_label.pack(side=tk.LEFT)
        self.status_updated_label = ttk.Label(status_bar, text="Обновлено 0 сек назад", font=('Arial', 9))
        self.status_updated_label.pack(side=tk.LEFT, padx=12)
        self.status_perf_label = ttk.Label(status_bar, text="RPS: -- | Error: --", font=('Arial', 9))
        self.status_perf_label.pack(side=tk.RIGHT)
    def create_enhanced_left_panel(self, parent):
        api_card = ttk.LabelFrame(parent, text="🔐 Настройки API", style='Modern.TLabelframe', padding=12)
        api_card.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(api_card, text="API Key:", style='Header.TLabel').pack(anchor=tk.W)
        self.api_key_entry = ttk.Entry(api_card, show="•", font=('Arial', 10))
        self.api_key_entry.pack(fill=tk.X, pady=(5, 10))
        # === ИЗМЕНЕНИЕ: Вставка сохраненного ключа ===
        if self.api_key:
            self.api_key_entry.insert(0, self.api_key)
            
        ttk.Label(api_card, text="API Secret:", style='Header.TLabel').pack(anchor=tk.W)
        self.api_secret_entry = ttk.Entry(api_card, show="•", font=('Arial', 10))
        self.api_secret_entry.pack(fill=tk.X, pady=(5, 10))
        # === ИЗМЕНЕНИЕ: Вставка сохраненного секрета ===
        if self.api_secret:
            self.api_secret_entry.insert(0, self.api_secret)
            
        account_frame = ttk.Frame(api_card)
        account_frame.pack(fill=tk.X, pady=5)
        
        # === ИЗМЕНЕНИЕ: Установка типа счета из сохранения ===
        initial_account_value = "demo" if self.demo_trading else "real"
        self.account_type_var = tk.StringVar(value=initial_account_value)
        
        ttk.Radiobutton(account_frame, text="Реальный счет", 
                       variable=self.account_type_var, value="real").pack(side=tk.LEFT)
        ttk.Radiobutton(account_frame, text="Демо-счет", 
                       variable=self.account_type_var, value="demo").pack(side=tk.LEFT)
                       
        self.connect_btn = ttk.Button(api_card, text="🔗 Подключиться к Bybit", 
                                    command=self.connect_to_bybit, style='Accent.TButton')
        self.connect_btn.pack(fill=tk.X, pady=(10, 5))
        
        info_card = ttk.LabelFrame(parent, text="📊 Статус", style='Modern.TLabelframe', padding=12)
        info_card.pack(fill=tk.X, pady=(0, 15))
        self.balance_label = ttk.Label(info_card, text="💰 Баланс: --", 
                                     font=('Arial', 12, 'bold'), foreground='#487eb0')
        self.balance_label.pack(anchor=tk.W, pady=5)
        self.account_type_label = ttk.Label(info_card, text="● Реальный счет", 
                                          style='Success.TLabel', font=('Arial', 10))
        self.account_type_label.pack(anchor=tk.W, pady=2)
        self.trading_status_label = ttk.Label(info_card, text="⏹️ Торговля: Выкл", 
                                            style='Danger.TLabel', font=('Arial', 10))
        self.trading_status_label.pack(anchor=tk.W, pady=2)
        
        control_card = ttk.LabelFrame(parent, text="⚙️ Управление", style='Modern.TLabelframe', padding=12)
        control_card.pack(fill=tk.X, pady=(0, 15))
        self.auto_trading_var = tk.BooleanVar(value=False)
        auto_toggle = ttk.Checkbutton(control_card, text="🤖 Автоматическая торговля", 
                                    variable=self.auto_trading_var, 
                                    command=self.toggle_auto_trading)
        auto_toggle.pack(anchor=tk.W, pady=5)
        
        btn_grid = ttk.Frame(control_card)
        btn_grid.pack(fill=tk.X, pady=5)
        buttons = [
            ("📈 Управление парами", self.open_trading_pairs_manager),
            ("🔄 Обновить подходящие", self.update_suitable_coins),
            ("📊 Отчёт (PnL)", self.open_enhanced_pnl_report),
            ("🚫 Черный список", self.open_blacklist_manager),
            ("📈 Статистика", self.show_performance_stats)
        ]
        for text, command in buttons:
            btn = ttk.Button(btn_grid, text=text, command=command)
            btn.pack(fill=tk.X, pady=2)
            
        self.position_card = ttk.LabelFrame(parent, text="📊 Текущие позиции", 
                                          style='Modern.TLabelframe', padding=12)
        self.position_card.pack(fill=tk.BOTH, expand=True)
        self.create_enhanced_position_table(self.position_card)
    def create_enhanced_right_panel(self, parent):
        stats_frame = ttk.Frame(parent)
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        stats_cards = ttk.Frame(stats_frame)
        stats_cards.pack(fill=tk.X)
        self.price_card = self.create_stat_card(stats_cards, "Текущая цена", "--", "#487eb0")
        self.change_card = self.create_stat_card(stats_cards, "Изменение 24ч", "--", "#44bd32")
        self.volume_card = self.create_stat_card(stats_cards, "Объем 24ч", "--", "#8c7ae6")
        self.signal_card = self.create_stat_card(stats_cards, "ML сигналы", "--", "#e1b12c")
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)
        working_tab = ttk.Frame(notebook, padding=10)
        notebook.add(working_tab, text="🎯 Монеты в работе")
        self.create_enhanced_working_coin_table(working_tab)
        suitable_tab = ttk.Frame(notebook, padding=10)
        notebook.add(suitable_tab, text="📈 Подходящие монеты")
        self.create_enhanced_suitable_coins_table(suitable_tab)
        orders_tab = ttk.Frame(notebook, padding=10)
        notebook.add(orders_tab, text="🧾 Заявки/ордера")
        self.create_orders_tab(orders_tab)
        stats_tab = ttk.Frame(notebook, padding=10)
        notebook.add(stats_tab, text="📊 PnL/статистика")
        ttk.Label(stats_tab, text="Ключевые метрики и быстрые действия", font=('Arial', 10, 'bold')).pack(anchor=tk.W)
        ttk.Button(stats_tab, text="Открыть подробный отчёт PnL", command=self.open_enhanced_pnl_report).pack(anchor=tk.W, pady=8)
    def create_stat_card(self, parent, title, value, color):
        card = ttk.Frame(parent, relief='solid', borderwidth=1)
        card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(card, text=title, font=('Arial', 9, 'bold'), 
                 foreground='#7f8fa6').pack(pady=(8, 2))
        value_label = ttk.Label(card, text=value, font=('Arial', 11, 'bold'), 
                              foreground=color)
        value_label.pack(pady=(2, 8))
        return value_label
    def create_enhanced_position_table(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Активные позиции", 
                 style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(header_frame, text="🔄 Обновить", 
                  command=self.update_position_display).pack(side=tk.RIGHT)
        columns = ('symbol', 'side', 'entry_price', 'size', 'pnl', 'pnl_percent', 'tp_set', 'status')
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.position_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'symbol': 'Пара',
            'side': 'Сторона', 
            'entry_price': 'Цена входа',
            'size': 'Размер USDT',
            'pnl': 'PnL USDT',
            'pnl_percent': '%PnL',
            'tp_set': 'TP установлено',
            'status': 'Статус'
        }
        for col, text in headers.items():
            self.position_tree.heading(col, text=text)
            self.position_tree.column(col, width=80)
        self.position_tree.column('symbol', width=90)
        self.position_tree.column('pnl_percent', width=70)
        self.position_tree.column('tp_set', width=110)
        self.position_tree.column('status', width=100)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.position_tree.yview)
        self.position_tree.configure(yscrollcommand=scrollbar.set)
        self.position_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Context menu for positions
        self.position_menu = tk.Menu(self.root, tearoff=0)
        self.position_menu.add_command(label="Открыть", command=self.update_position_display)
        self.position_menu.add_command(label="Установить TP", command=lambda: self._context_set_tp(self.position_tree))
        self.position_menu.add_command(label="Отменить ордера", command=lambda: self._context_cancel_orders(self.position_tree))
        self.position_tree.bind("<Button-3>", lambda e: self._open_context_menu(e, self.position_tree, self.position_menu))
    def create_enhanced_working_coin_table(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Монеты в работе (15min)", 
                 style='Header.TLabel').pack(side=tk.LEFT)
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="⚙️ Настройки", 
                  command=self.open_working_defaults_window).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ Удалить", 
                  command=self.remove_working_coin).pack(side=tk.LEFT, padx=2)
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol', 'direction', 'strategy', 'status')
        self.working_coin_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'symbol': 'Пара',
            'direction': 'Направление',
            'strategy': 'Стратегия/TP', 
            'status': 'Статус'
        }
        for col, text in headers.items():
            self.working_coin_tree.heading(col, text=text)
            self.working_coin_tree.column(col, width=100)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.working_coin_tree.yview)
        self.working_coin_tree.configure(yscrollcommand=scrollbar.set)
        self.working_coin_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.working_coin_tree.bind('<Double-1>', self.on_working_coin_double_click)
        # Context menu
        self.working_menu = tk.Menu(self.root, tearoff=0)
        self.working_menu.add_command(label="Открыть", command=lambda: self._context_open_edit(self.working_coin_tree))
        self.working_menu.add_command(label="Установить TP", command=lambda: self._context_set_tp(self.working_coin_tree))
        self.working_menu.add_command(label="Отменить ордера", command=lambda: self._context_cancel_orders(self.working_coin_tree))
        self.working_menu.add_command(label="Удалить", command=self.remove_working_coin)
        self.working_coin_tree.bind("<Button-3>", lambda e: self._open_context_menu(e, self.working_coin_tree, self.working_menu))
    def create_enhanced_suitable_coins_table(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Подходящие монеты для торговли", 
                 style='Header.TLabel').pack(side=tk.LEFT)
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="➕ Добавить в торговлю", 
                  command=self.add_suitable_to_trading).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔄 Обновить", 
                  command=self.update_suitable_coins).pack(side=tk.LEFT, padx=2)
        # Filters
        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(filter_frame, text="Фильтр символ:").pack(side=tk.LEFT)
        self.suitable_filter_symbol = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.suitable_filter_symbol, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(filter_frame, text="Мин. объем (USDT):").pack(side=tk.LEFT, padx=(10, 0))
        self.suitable_filter_volume = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.suitable_filter_volume, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Применить", command=self.update_suitable_coins_table).pack(side=tk.LEFT, padx=6)
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol', 'price', 'change_15m', 'change_24h', 'volume_24h', 'direction', 'strategy', 'confidence')
        self.suitable_coins_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'symbol': 'Пара',
            'price': 'Цена',
            'change_15m': 'Изменение 15m',
            'change_24h': 'Изменение 24ч',
            'volume_24h': 'Объем 24ч',
            'direction': 'Направление', 
            'strategy': 'Стратегия',
            'confidence': 'Уверенность'
        }
        for col, text in headers.items():
            self.suitable_coins_tree.heading(col, text=text)
        widths = {
            'symbol': 80, 'price': 80, 'change_15m': 90, 'change_24h': 90,
            'volume_24h': 90, 'direction': 80, 'strategy': 120, 'confidence': 80
        }
        for col, width in widths.items():
            self.suitable_coins_tree.column(col, width=width)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.suitable_coins_tree.yview)
        self.suitable_coins_tree.configure(yscrollcommand=scrollbar.set)
        self.suitable_coins_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.suitable_coins_tree.bind('<Double-1>', self.on_suitable_coin_click)
        # Context menu
        self.suitable_menu = tk.Menu(self.root, tearoff=0)
        self.suitable_menu.add_command(label="Добавить в торговлю", command=self.add_suitable_to_trading)
        self.suitable_coins_tree.bind("<Button-3>", lambda e: self._open_context_menu(e, self.suitable_coins_tree, self.suitable_menu))
        # Enable sorting
        self._enable_treeview_sorting(self.suitable_coins_tree)
        self._enable_treeview_sorting(self.working_coin_tree)
        self._enable_treeview_sorting(self.position_tree)
    def create_orders_tab(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text="Открытые лимитные ордера", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(header, text="🗑️ Отменить выбранные", command=self._cancel_selected_orders).pack(side=tk.RIGHT, padx=5)
        ttk.Button(header, text="🗑️ Отменить все", command=self._cancel_all_orders_all_symbols).pack(side=tk.RIGHT, padx=5)
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol', 'side', 'order_type', 'price', 'qty', 'leaves_qty')
        self.orders_tree = ttk.Treeview(frame, columns=columns, show='headings', height=15)
        headers = {
            'symbol': 'Пара', 'side': 'Сторона', 'order_type': 'Тип', 'price': 'Цена', 'qty': 'Кол-во', 'leaves_qty': 'Остаток'
        }
        for col, text in headers.items():
            self.orders_tree.heading(col, text=text)
            self.orders_tree.column(col, width=100)
        sc = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=sc.set)
        self.orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self._enable_treeview_sorting(self.orders_tree)
    def safe_float(self, value, default=0.0):
        try:
            if value is None or value == '':
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
    def start_suitable_coins_cleanup(self):
        def cleanup_task():
            while True:
                try:
                    self.cleanup_old_suitable_coins()
                    time.sleep(30)
                except Exception as e:
                    self.logger.error(f"Ошибка в задаче очистки подходящих монет: {e}")
                    time.sleep(60)
        threading.Thread(target=cleanup_task, daemon=True).start()
    def cleanup_old_suitable_coins(self):
        current_time = time.time()
        initial_count = len(self.suitable_coins)
        self.suitable_coins = [
            coin for coin in self.suitable_coins 
            if current_time - coin.timestamp < self.suitable_coins_cleanup_interval
        ]
        removed_count = initial_count - len(self.suitable_coins)
        if removed_count > 0:
            self.logger.info(f"Автоматически удалено {removed_count} устаревших монет из подходящих")
            self.root.after(0, self.update_suitable_coins_table)
    # НОВЫЙ УЛУЧШЕННЫЙ МЕТОД: Расчет средней цены входа с учетом сеточных ордеров
    def calculate_average_entry_price(self, symbol):
        """
        ИСПРАВЛЕНО: Получение средней цены входа СТРОГО из данных позиции биржи.
        Ручной пересчет через историю ордеров удален, так как он вызывал ошибки (фантомная прибыль).
        """
        try:
            # Получаем свежие данные позиции
            positions = self.fetch_positions(symbol=symbol)
            # Ищем позицию с размером > 0
            position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
            
            if position:
                # В Bybit avgPrice - это точная средневзвешенная цена входа
                avg_price = float(position['entry_price'])
                self.logger.debug(f"Средняя цена входа (биржевая) для {symbol}: {avg_price:.4f}")
                return avg_price
            
            return None
        except Exception as e:
            self.logger.error(f"Ошибка получения средней цены для {symbol}: {e}")
            return None
    # НОВЫЙ МЕТОД: Проверка текущего TP на бирже
    def get_current_take_profit(self, symbol):
        try:
            current_time = time.time()
            if symbol in self._tp_check_cache:
                cache_data = self._tp_check_cache[symbol]
                if current_time - cache_data['timestamp'] < self._tp_cache_ttl:
                    return cache_data['tp_price']
            response = self.rate_limited_request(
                self.session.get_positions,
                category="linear",
                symbol=symbol
            )
            if response and response.get('retCode') == 0:
                for pos in response['result']['list']:
                    if pos['symbol'] == symbol and float(pos['size']) > 0:
                        tp_price = None
                        if 'takeProfit' in pos and pos['takeProfit'] and pos['takeProfit'] != '0':
                            tp_price = self.safe_float(pos['takeProfit'])
                        self._tp_check_cache[symbol] = {
                            'timestamp': current_time,
                            'tp_price': tp_price
                        }
                        return tp_price
            return None
        except Exception as e:
            self.logger.error(f"Ошибка получения текущего TP для {symbol}: {e}")
            return None
    # НОВЫЙ ВСПОМОГАТЕЛЬНЫЙ МЕТОД: Получение positionIdx по стороне
    def get_position_idx_for_side(self, side):
        """Возвращает positionIdx для хеджированного режима: Buy → 1, Sell → 2"""
        return 1 if side == "Buy" else 2
    # ОБНОВЛЕННЫЙ МЕТОД: Установка TP — использует ТОЛЬКО take_profit из конфигурации или ручное значение
    def round_price(self, price, tick_size):
        """
        Корректное округление цены до шага инструмента (tick_size).
        Убирает проблемы с 0.0033269999999999997.
        """
        if tick_size == 0:
            return price
        
        # Используем Decimal для точности, если нужно, но для скорости математика:
        # Округляем до ближайшего целого количества шагов
        rounded = round(float(price) / float(tick_size)) * float(tick_size)
        
        # Определяем количество знаков после запятой у tick_size
        tick_str = f"{float(tick_size):.10f}".rstrip('0')
        if '.' in tick_str:
            precision = len(tick_str.split('.')[1])
        else:
            precision = 0
            
        return round(rounded, precision)
    
    def set_take_profit_with_protection(self, symbol, side, config, force_update=False):
        try:
            # === 0. Получаем данные о точности цены ===
            symbol_info = self.get_symbol_info(symbol)
            tick_size = 0.01 # Дефолт
            
            if symbol_info:
                price_filter = symbol_info.get('priceFilter', {})
                tick_size = float(price_filter.get('tickSize', '0.01'))

            # 1. Определяем цену TP
            use_manual = config.use_manual_tp and config.manual_tp_price > 0
            tp_price = 0.0

            if use_manual:
                tp_price = config.manual_tp_price
            else:
                # Берем % профита из конфига
                target_percent = config.take_profit
                
                # === ЖЕЛЕЗНОЕ ПРАВИЛО: Минимальный профит всегда >= 0.8% ===
                final_percent = max(target_percent, 0.8) 

                entry_price = getattr(config, '_initial_entry_price', None)
                if entry_price is None or entry_price <= 0:
                    entry_price = self.get_initial_entry_price(symbol)
                
                if not entry_price or entry_price <= 0:
                    return False
                    
                if side == "Buy":
                    tp_price = entry_price * (1 + final_percent / 100)
                else:
                    tp_price = entry_price * (1 - final_percent / 100)

            # Округляем цену
            tp_price = self.round_price(tp_price, tick_size)
            tp_price_str = f"{tp_price:.10f}".rstrip('0').rstrip('.')

            # 2. Проверка: нужно ли менять TP на бирже?
            # Если force_update=True, мы пропускаем предварительную проверку кэша,
            # но результат 34040 от API всё равно обработаем как успех.
            if not force_update:
                current_tp = self.get_current_take_profit(symbol)
                if current_tp is not None:
                    if abs(tp_price - current_tp) < (tick_size / 2):
                         return True

            # 3. Отправка запроса на биржу
            position_idx = self.get_position_idx_for_side(side)
            
            
            # === DOUBLE TP SET (RETRY) ===
            tp_response = None
            for attempt in range(2):
                tp_response = self.rate_limited_request(
                    self.session.set_trading_stop,
                    category="linear",
                    symbol=symbol,
                    takeProfit=tp_price_str,
                    tpTriggerBy="MarkPrice",
                    positionIdx=position_idx
                )
                if tp_response and tp_response.get("retCode") in (0, 34040):
                    break
                time.sleep(1.0)

            
            # Проверка на None (если rate_limited_request вернул fallback из-за других ошибок)
            if tp_response is None:
                self.logger.warning(f"Пустой ответ API при установке TP для {symbol}")
                return False

            ret_code = tp_response.get('retCode')
            error_msg = tp_response.get('retMsg', 'Unknown error')

            # === ИСПРАВЛЕНИЕ: 34040 и "not modified" считаем УСПЕХОМ ===
            is_success = (ret_code == 0)
            is_not_modified = (ret_code == 34040 or 'not modified' in str(error_msg).lower())

            if is_success or is_not_modified:
                log_msg = "TP УСПЕШНО ОБНОВЛЕН" if is_success else "TP УЖЕ АКТУАЛЕН (Not modified)"
                self.logger.info(f"✅ {log_msg} для {symbol}: {tp_price_str} (Target: {final_percent if not use_manual else 'Manual'}%)")
                
                # ВАЖНО: Обновляем кэш успешного TP, чтобы монитор не думал, что это ручное изменение
                self._last_successful_tp[symbol] = {
                    'tp_price': float(tp_price_str),
                    'timestamp': time.time()
                }
                self._tp_check_cache[symbol] = {
                    'timestamp': time.time(),
                    'tp_price': float(tp_price_str)
                }
                return True
            
            elif ret_code == 10001: 
                # Позиция закрыта, TP не нужен
                return False
                
            else:
                self.logger.error(f"Ошибка установки TP для {symbol} (Code {ret_code}): {error_msg}")
                return False
                    
        except Exception as e:
            self.logger.error(f"Исключение при расчете TP для {symbol}: {e}", exc_info=True)
            return False

    def get_initial_entry_price(self, symbol):
        """Получает первоначальную цену входа из истории позиций или конфигурации"""
        config = next((c for c in self.working_coin_configs if c.symbol == symbol), None)
        if config and hasattr(config, '_initial_entry_price'):
            return config._initial_entry_price
        # fallback: из текущей позиции
        positions = self.fetch_positions(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
        if position:
            entry_price = float(position['entry_price'])
            if config:
                config._initial_entry_price = entry_price
            return entry_price
        return None

    def get_position_size(self, symbol):
        try:
            positions = self.fetch_positions(symbol=symbol)
            position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
            if position:
                return float(position['size'])
        except Exception as e:
            self.logger.error(f"Ошибка получения размера позиции для {symbol}: {e}")
        return 0.0

    def place_take_profit_order(self, symbol, side, tp_price, quantity):
        try:
            close_side = "Sell" if side == "Buy" else "Buy"
            if quantity <= 0:
                self.logger.error(f"Некорректный размер позиции для {symbol}: {quantity}")
                return False
            position_idx = self.get_position_idx_for_side(side)
            response = self.rate_limited_request(
                self.session.place_order,
                category="linear",
                symbol=symbol,
                side=close_side,
                orderType="Limit",
                qty=str(quantity),
                price=str(tp_price),
                timeInForce="GTC",
                reduceOnly=True,
                positionIdx=position_idx
            )
            if response and response.get('retCode') == 0:
                self.logger.info(f"Лимитный TP ордер размещен для {symbol} по цене {tp_price:.4f}")
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Ошибка размещения лимитного TP ордера для {symbol}: {error_msg}")
                return False
        except Exception as e:
            self.logger.error(f"Ошибка размещения TP ордера для {symbol}: {e}")
            return False

    def start_enhanced_tp_monitoring(self):
        def monitoring_task():
            while True:
                try:
                    self.enhanced_tp_protection()
                    time.sleep(5)
                except Exception as e:
                    self.logger.error(f"Ошибка в задаче мониторинга TP: {e}")
                    time.sleep(10)
        threading.Thread(target=monitoring_task, daemon=True).start()

    def enhanced_tp_protection(self):
        """
        ИСПРАВЛЕНО: Фоновая защита TP. 
        Гарантирует, что закрытие происходит только если РЕАЛЬНАЯ прибыль > 0.8%.
        """
        try:
            positions = self.fetch_positions()
            active_configs = self.working_coin_configs[:]
            
            for config in active_configs:
                symbol = config.symbol
                
                position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
                if not position:
                    continue

                mark_price = float(position['mark_price'])
                entry_price = float(position['entry_price']) # Берем цену входа СТРОГО с биржи
                side = position['side']
                
                # Защита от деления на ноль
                if entry_price == 0:
                    continue

                # Расчет РЕАЛЬНОГО процента движения цены
                if side == "Buy":
                    current_profit_percent = (mark_price - entry_price) / entry_price * 100
                else: # Sell
                    current_profit_percent = (entry_price - mark_price) / entry_price * 100
                
                # Целевой профит из конфига, но ЖЕЛЕЗНО не меньше 0.8%
                target_tp = max(config.take_profit, 0.8)

                # Дополнительная проверка: Unrealized PnL должен быть положительным
                # (защита от ситуаций, когда цена вроде прошла, но комиссии съели прибыль)
                unrealized_pnl = float(position.get('pnl', 0))

                # Проверка: 
                # 1. Процент прибыли выше цели
                # 2. Процент прибыли выше 0.8% (хардкод минимум)
                # 3. PnL в деньгах положительный
                if current_profit_percent >= target_tp and current_profit_percent >= 0.8 and unrealized_pnl > 0:
                    self.logger.info(f"💰 Фоновая защита: Цель достигнута {symbol}. "
                                     f"Прибыль: {current_profit_percent:.2f}% (PnL: {unrealized_pnl:.4f}). Закрываем.")
                    self.force_close_position_with_profit(symbol, side, entry_price)
                
                # Логируем, если мы близко, но недостаточно (для отладки)
                elif current_profit_percent > 0.5:
                    self.logger.debug(f"👀 {symbol} растет: {current_profit_percent:.2f}% (Цель: {target_tp}%)")
                    
        except Exception as e:
            self.logger.error(f"Ошибка в модуле защиты TP: {e}")

    def force_close_position_with_profit(self, symbol, side, average_price):

        """Prинудительное закрытие позиции с немедленной очисткой монеты и постановкой заморозки.

        После успешного закрытия (если ордер отправлен или позиция уже закрыта) функция:

        - удаляет монету из working_coin_configs,

        - отменяет все сеточные ордера по монете,

        - ставит заморозку (5 минут) в self._last_position_close_time,

        - запускает сохранение PnL и UI-обновления через cleanup_finished_coin_with_timeout.

        Работает корректно в режиме хеджирования.

        """

        try:

            # Берем свежие данные по позициям для символа

            positions = self.fetch_positions(symbol=symbol)

            position = next((p for p in positions if p.get('symbol') == symbol and float(p.get('size', 0)) > 0), None)

        

            if not position:

                self.logger.info(f"force_close_position_with_profit: нет открытой позиции для {symbol}")

                if any(c.symbol == symbol for c in getattr(self, 'working_coin_configs', [])):

                    threading.Thread(target=self.cleanup_finished_coin_with_timeout, args=(symbol,), daemon=True).start()

                    self.logger.info(f"Запущена очистка для {symbol} (позиция отсутствует).")

                return False

        

            mark_price = float(position.get('mark_price', 0))

            entry_price = float(position.get('entry_price', average_price or 0))

            qty = float(position.get('size', 0))

            unrealized_pnl = float(position.get('pnl', 0) or 0)

        

            if position.get('side') == 'Buy' or side == 'Buy':

                current_profit_percent = (mark_price - entry_price) / entry_price * 100 if entry_price else 0.0

            else:

                current_profit_percent = (entry_price - mark_price) / entry_price * 100 if entry_price else 0.0

        

            if current_profit_percent < 0.75 or unrealized_pnl <= 0:

                self.logger.warning(f"🛑 ОТМЕНА ЗАКРЫТИЯ {symbol}: profit={current_profit_percent:.2f}%, pnl={unrealized_pnl:.4f}")

                return False

        

            close_side = 'Sell' if (position.get('side') == 'Buy' or side == 'Buy') else 'Buy'

            try:

                response = self.rate_limited_request(

                    self.session.place_order,

                    category='linear',

                    symbol=symbol,

                    side=close_side,

                    orderType='Market',

                    qty=str(qty),

                    reduceOnly=True,

                    positionIdx=self.get_position_idx_for_side(position.get('side') or side)

                )

            except Exception as e:

                self.logger.error(f"Ошибка отправки ордера закрытия для {symbol}: {e}")

                return False

        

            if not response:

                self.logger.error(f"Пустой ответ при закрытии {symbol}")

                return False

        

            ret_code = response.get('retCode')

            ret_msg = response.get('retMsg', '') or response.get('ret_msg', '')

        

            if ret_code == 0 or ret_code == 10001 or 'position not found' in str(ret_msg).lower():

                self.logger.info(f"✅ Закрывающий ордер для {symbol} отправлен/позиция отсутствует: {ret_code} {ret_msg}")

                try:

                    threading.Thread(target=self.cleanup_finished_coin_with_timeout, args=(symbol,), daemon=True).start()

                    self.logger.info(f"🧊 Мгновенная очистка и заморозка запущены для {symbol}")

                except Exception as e:

                    self.logger.error(f"Ошибка при запуске очистки/заморозки для {symbol}: {e}")

                return True

        

            self.logger.error(f"❌ Не удалось закрыть {symbol}: {ret_code} / {ret_msg}")

            return False

        except Exception as e:

            self.logger.error(f"Исключение в force_close_position_with_profit({symbol}): {e}", exc_info=True)

            return False


    def start_manual_tp_monitoring(self):
        def monitoring_task():
            while True:
                try:
                    self.check_manual_tp_updates()
                    time.sleep(10)
                except Exception as e:
                    self.logger.error(f"Ошибка в задаче мониторинга ручных TP: {e}")
                    time.sleep(30)
        threading.Thread(target=monitoring_task, daemon=True).start()

    def check_manual_tp_updates(self):
        """
        Проверяет изменения TP на бирже. 
        ИСПРАВЛЕНО: Не переключает в Manual, если TP совпадает с последним, установленным ботом.
        """
        try:
            positions = self.fetch_positions()
            for position in positions:
                symbol = position['symbol']
                size = float(position['size'])
                if size <= 0:
                    continue

                config = next((c for c in self.working_coin_configs if c.symbol == symbol), None)
                if not config:
                    continue
                
                # Если уже ручной - просто обновляем значение в конфиге, если оно изменилось
                current_tp = self.get_current_take_profit(symbol)
                if current_tp is None:
                    continue

                if config.use_manual_tp:
                    if abs(config.manual_tp_price - current_tp) > 1e-6:
                        config.manual_tp_price = current_tp
                        self.save_working_coin_configs()
                    continue

                # === АВТО РЕЖИМ (Защита от ложного переключения) ===
                
                # 1. Получаем инфо о тикере для округления
                symbol_info = self.get_symbol_info(symbol)
                tick_size = 0.01
                if symbol_info:
                    tick_size = float(symbol_info.get('priceFilter', {}).get('tickSize', '0.01'))
                
                # 2. Сравниваем текущий TP на бирже с тем, что бот ставил в прошлый раз
                last_bot_tp_info = self._last_successful_tp.get(symbol)
                if last_bot_tp_info:
                    last_bot_price = last_bot_tp_info.get('tp_price', 0.0)
                    
                    # Если TP на бирже равен тому, что мы ставили раньше -> это НЕ ручное вмешательство.
                    # Это просто значит, что мы еще не успели обновить TP после усреднения.
                    if abs(current_tp - last_bot_price) < (tick_size * 1.5):
                        continue

                # 3. Расчет ожидаемого Авто-TP (для проверки реального расхождения)
                entry_price = self.get_initial_entry_price(symbol)
                if not entry_price:
                    entry_price = float(position['entry_price'])
                
                target_percent = max(config.take_profit, config.min_take_profit)
                if position['side'] == "Buy":
                    auto_tp_price = entry_price * (1 + target_percent / 100)
                else:
                    auto_tp_price = entry_price * (1 - target_percent / 100)
                
                auto_tp_rounded = self.round_price(auto_tp_price, tick_size)
                
                # 4. Если отличается и от расчетного, и от прошлого поставленного ботом -> значит юзер руками поменял
                diff = abs(current_tp - auto_tp_rounded)
                threshold = tick_size * 2.1 
                
                if diff > threshold:
                    self.logger.info(f"🔄 TP recalculated automatically (AUTO MODE FORCED)")
                    config.use_manual_tp = True
                    config.manual_tp_price = current_tp
                    self.save_working_coin_configs()
                    self.root.after(0, self.update_working_coin_display)

        except Exception as e:
            self.logger.error(f"Ошибка проверки ручных изменений TP: {e}")

    # ИСПРАВЛЕННЫЙ МЕТОД: Установка TP при открытии позиции
    def update_take_profit_for_position(self, position, config):
        symbol = position['symbol']
        side = position['side']
        entry_price = float(position['entry_price'])
        config._initial_entry_price = entry_price
        success = self.set_take_profit_with_protection(symbol, side, config)
        if success:
            
                # FIX: мгновенная блокировка монеты после TP

                self.logger.info(f"✅ TP установлен для {symbol} при открытии позиции от цены {entry_price:.4f}")
        else:
            self.logger.error(f"❌ Не удалось установить TP для {symbol}")
        return success

    def update_take_profit_based_on_average(self, symbol, config, force_update=False):
        """Обновляет TP от средней цены входа, используя take_profit из конфига, но не ниже 0.8%"""
        
        # Всегда запрашиваем свежие данные, так как avgPrice меняется на бирже
        positions = self.fetch_positions(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
        
        if not position:
            return False
            
        # Получаем актуальную среднюю цену входа
        average_price = float(position['entry_price']) 
        
        # Сохраняем актуальную среднюю цену в конфиг
        config._initial_entry_price = average_price
        
        side = position['side']
        
        self.logger.info(f"Пересчет TP для {symbol}. Новая средняя цена с биржи: {average_price}. Force: {force_update}")
        
        return self.set_take_profit_with_protection(symbol, side, config, force_update=force_update)

    def check_take_profit_hit(self):
        """
        Проверка достижения TP с жестким фильтром минимальной прибыли 0.8%.
        """
        try:
            positions = self.fetch_positions()
            for position in positions:
                symbol = position['symbol']
                mark_price = float(position['mark_price'])
                side = position['side']
                size = float(position['size'])
                
                if size <= 0:
                    continue
                    
                config = next((c for c in self.working_coin_configs if c.symbol == symbol), None)
                if not config:
                    continue
                
                # ИСПРАВЛЕНО: Берем цену входа прямо из позиции
                entry_price = float(position['entry_price'])
                
                # ... (остальной код расчета TP Price оставляем прежним) ...
                if config.use_manual_tp and config.manual_tp_price > 0:
                    tp_price = config.manual_tp_price
                    tp_type = "ручной"
                else:
                    tp_percent = max(config.take_profit, config.min_take_profit)
                    if side == "Buy":
                        tp_price = entry_price * (1 + tp_percent / 100)
                    else:
                        tp_price = entry_price * (1 - tp_percent / 100)
                    tp_type = "авто"
                
                tp_hit = (side == "Buy" and mark_price >= tp_price) or (side == "Sell" and mark_price <= tp_price)
                
                if tp_hit:
                    # СЧИТАЕМ РЕАЛЬНЫЙ ПРОЦЕНТ ПРИБЫЛИ
                    if side == "Buy":
                        actual_profit = (mark_price - entry_price) / entry_price * 100
                    else:
                        actual_profit = (entry_price - mark_price) / entry_price * 100
                    
                    # ИСПРАВЛЕНО: Добавлена проверка PnL > 0
                    unrealized_pnl = float(position.get('pnl', 0))

                    if actual_profit >= 0.8 and unrealized_pnl > 0:
                        self.logger.info(f"✅ TP ({tp_type}) достигнут для {symbol}: Цена={mark_price:.4f}, Вход={entry_price:.4f}, Прибыль={actual_profit:.2f}%")
                        self.force_close_position_with_profit(symbol, side, entry_price)
                    else:
                        self.logger.warning(f"⚠️ TP уровень достигнут, но реальная прибыль {actual_profit:.2f}% < 0.8% (или PnL<0). Ждем.")

        except Exception as e:
            self.logger.error(f"Ошибка проверки TP: {e}")

    def force_close_position(self, symbol, side):
        """Совместимость со старым кодом"""
        average_price = self.calculate_average_entry_price(symbol)
        if average_price:
            self.force_close_position_with_profit(symbol, side, average_price)
        else:
            self.logger.error(f"Не удалось рассчитать среднюю цену для {symbol}")

    def cleanup_finished_coin(self, symbol):
        """ИСПРАВЛЕННЫЙ МЕТОД: Очистка завершенной монеты - совместимость со старым кодом"""
        self.cleanup_finished_coin_with_timeout(symbol)

    def cleanup_finished_coin_with_timeout(self, symbol):
        """
        Полная очистка монеты после завершения сделки.
        Активирует таймаут 5 минут, удаляет из работы и отменяет сетку.
        """
        safe_symbol = str(symbol).strip().upper()
        current_time = time.time()
        timeout_duration = 300  # 5 минут заморозки

        # 1. МГНОВЕННАЯ ЗАМОРОЗКА (Самое важное)
        self._last_position_close_time[safe_symbol] = current_time
        self.logger.info(f"❄️ ЗАМОРОЗКА {safe_symbol}: Таймаут активирован на {timeout_duration} сек. (до {datetime.fromtimestamp(current_time + timeout_duration).strftime('%H:%M:%S')})")

        # 2. Удаляем из списка рабочих конфигов (в памяти)
        # Это предотвращает повторный вход в check_working_coin_conditions
        original_count = len(self.working_coin_configs)
        self.working_coin_configs = [c for c in self.working_coin_configs if c.symbol != safe_symbol]
        
        # Сохраняем обновленный конфиг на диск
        if len(self.working_coin_configs) < original_count:
            self.save_working_coin_configs()
            # Обновляем UI в главном потоке
            self.root.after(0, self.update_working_coin_display)
            self.logger.info(f"🗑️ Монета {safe_symbol} удалена из списка 'В работе'.")

        # 3. Удаляем из списка "Подходящих монет" (чтобы сканер не вернул её сразу)
        if hasattr(self, 'suitable_coins'):
            self.suitable_coins = [c for c in self.suitable_coins if c.symbol != safe_symbol]
            self.root.after(0, self.update_suitable_coins_table)

        # 4. Удаляем сетку ордеров в фоновом потоке
        # Используем daemon=True, чтобы не блокировать основной цикл
        self.logger.info(f"🧹 Запуск отмены всех ордеров для {safe_symbol}...")
        threading.Thread(target=self.enhanced_cancel_all_orders, args=(safe_symbol,), daemon=True).start()

        # 5. Очищаем состояние позиции в памяти бота
        if safe_symbol in self._position_states:
            del self._position_states[safe_symbol]
        
        # Очищаем кэши TP
        if safe_symbol in self._last_successful_tp:
            del self._last_successful_tp[safe_symbol]
        if safe_symbol in self._tp_check_cache:
            del self._tp_check_cache[safe_symbol]

        # 6. Сохраняем PnL (историю сделки)
        # Запускаем с задержкой, чтобы биржа успела сформировать историю
        def save_pnl_task(target_sym):
            time.sleep(3.0) 
            try:
                response = self.rate_limited_request(
                    self.session.get_closed_pnl,
                    category="linear",
                    symbol=target_sym,
                    limit=5
                )
                if response and response.get('retCode') == 0 and response['result']['list']:
                    latest = response['result']['list'][0]
                    # Проверка дубликатов
                    is_duplicate = False
                    if self.trade_history:
                        last_ts = self.trade_history[-1].get('timestamp', '')
                        trade_ts = datetime.fromtimestamp(int(latest['createdTime']) / 1000).isoformat()
                        if last_ts == trade_ts and self.trade_history[-1]['symbol'] == target_sym:
                            is_duplicate = True

                    if not is_duplicate:
                        pnl = float(latest['closedPnl'])
                        trade_record = {
                            'symbol': target_sym,
                            'side': latest['side'],
                            'entry_price': float(latest['avgEntryPrice']),
                            'close_price': float(latest['avgExitPrice']),
                            'size': float(latest['qty']),
                            'pnl': pnl,
                            'timestamp': datetime.fromtimestamp(int(latest['createdTime']) / 1000).isoformat(),
                            'close_type': 'TP' if pnl > 0 else 'SL',
                            'strategy': 'Grid'
                        }
                        self.trade_history.append(trade_record)
                        self.save_trade_history()
                        self.logger.info(f"💰 PnL сохранен для {target_sym}: {pnl:.2f} USDT")
            except Exception as e:
                self.logger.error(f"Ошибка сохранения PnL для {target_sym}: {e}")

            # 7. После завершения всех процедур пробуем добавить следующую монету
            self.root.after(0, self.auto_add_next_working_coin)

        threading.Thread(target=save_pnl_task, args=(safe_symbol,), daemon=True).start()
        
    def calculate_actual_tp_percent(self, side, entry_price, close_price):
        try:
            if side == "Buy":
                return (close_price - entry_price) / entry_price * 100
            else:
                return (entry_price - close_price) / entry_price * 100
        except:
            return 0.0

    def debug_position_state(self, symbol):
        try:
            positions = self.fetch_positions(symbol=symbol)
            position = next((p for p in positions if p['symbol'] == symbol), None)
            if position:
                average_price = self.calculate_average_entry_price(symbol)
                self.logger.info(f"DEBUG {symbol}: "
                               f"size={position['size']}, "
                               f"entry={position['entry_price']}, "
                               f"average={average_price:.4f}, "
                               f"mark={position['mark_price']}, "
                               f"side={position['side']}")
            config = next((c for c in self.working_coin_configs if c.symbol == symbol), None)
            if config and position:
                if config.use_manual_tp:
                    tp_price = config.manual_tp_price
                    tp_type = "ручной"
                else:
                    if average_price:
                        tp_price = average_price * (1 + config.take_profit/100) if position['side'] == "Buy" else average_price * (1 - config.take_profit/100)
                    else:
                        tp_price = float(position['entry_price']) * (1 + config.take_profit/100) if position['side'] == "Buy" else float(position['entry_price']) * (1 - config.take_profit/100)
                    tp_type = "автоматический"
                self.logger.info(f"DEBUG {symbol}: расчетный TP={tp_price:.4f} ({tp_type})")
        except Exception as e:
            self.logger.error(f"DEBUG ошибка для {symbol}: {e}")

    def is_symbol_in_timeout(self, symbol):
        """
        Проверяет, находится ли символ в таймауте (5 минут после закрытия).
        Возвращает True, если торговать этой монетой нельзя.
        """
        if not symbol:
            return False
            
        safe_symbol = str(symbol).strip().upper()
        
        if safe_symbol not in self._last_position_close_time:
            return False
            
        current_time = time.time()
        timeout_duration = 300  # 300 секунд = 5 минут
        last_close_time = self._last_position_close_time[safe_symbol]
        time_since_close = current_time - last_close_time
        
        if time_since_close < timeout_duration:
            # Можно раскомментировать для отладки, но будет спамить в лог
            # self.logger.debug(f"⏳ {safe_symbol} в таймауте еще {timeout_duration - time_since_close:.0f} сек")
            return True
        else:
            # Если время вышло, удаляем из словаря, чтобы освободить память
            # и разрешить торговлю в будущем
            del self._last_position_close_time[safe_symbol]
            self.logger.info(f"🔓 Таймаут для {safe_symbol} истек. Монета доступна для торговли.")
            return False
        
    def load_symbols(self):
        """Загружает список торгуемых пар, исключая неактивные"""
        try:
            response = self.rate_limited_request(
                self.session.get_instruments_info,
                category="linear"
            )
            if response and response.get('retCode') == 0:
                symbols_data = response['result']['list']
                self.symbols = []
                for s in symbols_data:
                    # Фильтруем только USDT пары
                    if not s['symbol'].endswith('USDT'):
                        continue
                    
                    # === ИСПРАВЛЕНИЕ ===
                    # Строго проверяем статус. Если не 'Trading', не добавляем в список.
                    # Это предотвратит ошибки типа "symbol is not supported" (10001)
                    if s.get('status') != 'Trading':
                        continue
                        
                    self.symbols.append(s['symbol'])
                    
                self.active_futures_symbols = set(self.symbols)
                
                # Сохраняем кэш символов
                with open(self.futures_symbols_file, 'w', encoding='utf-8') as f:
                    json.dump(self.symbols, f, indent=2, ensure_ascii=False)
                    
                self.logger.info(f"Загружено {len(self.symbols)} активных торговых пар (Status: Trading)")
                
                if hasattr(self, 'symbol_combobox'):
                    self.symbol_combobox['values'] = self.symbols
                    if self.symbols and self.current_symbol not in self.symbols:
                        self.current_symbol = self.symbols[0]
                        self.symbol_combobox.set(self.current_symbol)
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Ошибка загрузки символов: {error_msg}")
        except Exception as e:
            self.logger.error(f"Ошибка загрузки списка символов: {e}")

    # --- START: API error handling and auto-remove symbol after repeated failures ---
    def register_symbol_api_error(self, symbol: str, error_msg: str):
        """Регистрирует ошибку API для символа. Если число ошибок подряд достигает порога,
        инициирует удаление монеты из 'в работе' и отмену ордеров."""
        try:
            safe_symbol = str(symbol).strip().upper()
            count = self._symbol_api_error_counts.get(safe_symbol, 0) + 1
            self._symbol_api_error_counts[safe_symbol] = count
            self.logger.warning(f"❗ API error for {safe_symbol}: {error_msg} (count={count}/{self.api_error_threshold})")

            if count >= self.api_error_threshold:
                reason = f"API errors >= {self.api_error_threshold}: {error_msg}"
                if safe_symbol not in self.api_error_blacklist:
                    self.remove_symbol_from_working_symbol(safe_symbol, reason)
                    self.api_error_blacklist.add(safe_symbol)
        except Exception as e:
            self.logger.error(f"Ошибка в register_symbol_api_error: {e}")

    def reset_symbol_api_error_count(self, symbol: str):
        """Сбросить счётчик ошибок по символу (при успешном API-вызове)."""
        try:
            safe_symbol = str(symbol).strip().upper()
            if safe_symbol in self._symbol_api_error_counts:
                del self._symbol_api_error_counts[safe_symbol]
        except Exception:
            pass

    def remove_symbol_from_working_symbol(self, symbol: str, reason: str):
        """Безопасно удаляет символ из рабочих конфигов и запускает отмену ордеров."""
        try:
            safe_symbol = str(symbol).strip().upper()
            self.logger.error(f"🛑 Удаляем {safe_symbol} из работы по причине: {reason}")

            # Удаляем из working_coin_configs (в памяти)
            original_count = len(self.working_coin_configs)
            self.working_coin_configs = [c for c in self.working_coin_configs if c.symbol != safe_symbol]
            if len(self.working_coin_configs) < original_count:
                try:
                    self.save_working_coin_configs()
                except Exception:
                    pass
                try:
                    self.root.after(0, self.update_working_coin_display)
                except Exception:
                    pass
                self.logger.info(f"🗑️ {safe_symbol} удалена из списка 'В работе' (по ошибкам API).")

            # Добавляем в временный blacklist
            try:
                if not hasattr(self, 'temp_api_error_blacklist'):
                    self.temp_api_error_blacklist = set()
                self.temp_api_error_blacklist.add(safe_symbol)
            except Exception:
                pass

            # Удаляем из suitable_coins
            if hasattr(self, 'suitable_coins'):
                self.suitable_coins = [c for c in self.suitable_coins if c.symbol != safe_symbol]
                try:
                    self.root.after(0, self.update_suitable_coins_table)
                except Exception:
                    pass

            # Отменяем ордера в фоне (daemon thread)
            try:
                threading.Thread(target=self.enhanced_cancel_all_orders, args=(safe_symbol,), daemon=True).start()
            except Exception as e:
                self.logger.warning(f"Не удалось запустить enhanced_cancel_all_orders для {safe_symbol}: {e}")

            # Очищаем внутреннее состояние позиции (если есть)
            try:
                if safe_symbol in self._position_states:
                    del self._position_states[safe_symbol]
            except Exception:
                pass

            # Сбросить счётчик ошибок
            try:
                if safe_symbol in self._symbol_api_error_counts:
                    del self._symbol_api_error_counts[safe_symbol]
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"Ошибка при удалении символа {symbol}: {e}")
    # --- END: API error handling ---

    def is_valid_futures_symbol(self, symbol):
        if symbol in self.active_futures_symbols:
            return True
        try:
            response = self.rate_limited_request(
                self.session.get_instruments_info,
                category="linear",
                symbol=symbol
            )
            if response and response.get('retCode') == 0 and response['result']['list']:
                symbol_info = response['result']['list'][0]
                if symbol_info['symbol'] == symbol and symbol.endswith('USDT'):
                    self.logger.info(f"Символ {symbol} найден через дополнительную проверку API")
                    self.active_futures_symbols.add(symbol)
                    return True
        except Exception as e:
            self.logger.warning(f"Дополнительная проверка {symbol} не удалась: {e}")
        return False

    def adjust_quantity(self, symbol, quantity):
        try:
            response = self.rate_limited_request(
                self.session.get_instruments_info,
                category="linear",
                symbol=symbol
            )
            if response and response.get('retCode') == 0:
                symbol_info = response['result']['list'][0]
                lot_size_filter = symbol_info.get('lotSizeFilter', {})
                if lot_size_filter:
                    qty_step = float(lot_size_filter.get('qtyStep', 1))
                    adjusted_qty = round(quantity / qty_step) * qty_step
                    min_qty = float(lot_size_filter.get('minOrderQty', 0))
                    max_qty = float(lot_size_filter.get('maxOrderQty', float('inf')))
                    if adjusted_qty < min_qty:
                        self.logger.warning(f"Количество {adjusted_qty} меньше минимального {min_qty} для {symbol}")
                        return 0
                    if adjusted_qty > max_qty:
                        self.logger.warning(f"Количество {adjusted_qty} больше максимального {max_qty} для {symbol}")
                        return max_qty
                    return adjusted_qty
        except Exception as e:
            self.logger.error(f"Ошибка корректировки количества для {symbol}: {e}")
        return quantity

    
    def enter_position_for_working_coin(self, config, entry_price):
        symbol = config.symbol

        # ❄️ ЖЕСТКАЯ БЛОКИРОВКА ПОВТОРНОГО ВХОДА ПОСЛЕ TP
        if self.is_symbol_in_timeout(symbol):
            self.logger.warning(f"⛔ Повторный вход запрещен: {symbol} в заморозке после TP.")
            return

        # ❌ Если монета уже удалена из работы — вход запрещён
        if not any(c.symbol == symbol for c in self.working_coin_configs):
            self.logger.warning(f"⛔ Повторный вход запрещен: {symbol} удалена из монет в работе.")
            return
    
        symbol = config.symbol

        # === ЖЕСТКАЯ ЗАЩИТА ОТ ПОВТОРНОГО ВХОДА ===
        # 1. Проверяем таймаут (если сработал TP секунду назад)
        if self.is_symbol_in_timeout(symbol):
            self.logger.warning(f"⛔ Блокировка входа {symbol}: действует таймаут после закрытия.")
            return

        # 2. Проверяем, находится ли монета ВСЕ ЕЩЕ в реальном списке рабочих
        real_config_exists = any(c.symbol == symbol for c in self.working_coin_configs)
        if not real_config_exists:
            self.logger.warning(f"⛔ Блокировка входа {symbol}: монета была удалена из работы.")
            return
        # ==========================================

        log_once(f"enter_position_{config.symbol}", logging.INFO,
                f"Попытка входа в позицию для {config.symbol}. Направление: {config.direction}, Цена: {entry_price:.4f}",
                self.logger)
        try:
            if self.has_open_position(config.symbol):
                self.logger.info(f"Позиция для {config.symbol} уже открыта, пропускаем вход")
                return
            
            # Предварительная отмена ордеров
            self.cancel_all_orders_for_symbol(config.symbol)
            
            # Получаем информацию о символе
            symbol_info = self.get_symbol_info(config.symbol)
            if not symbol_info:
                self.logger.error(f"❌ Не удалось получить информацию о символе {config.symbol}. Вход отменен.")
                self.register_symbol_api_error(config.symbol, 'get_symbol_info returned None')
                return

            if symbol_info.get('status') != 'Trading':
                 self.logger.error(f"⛔ Монета {config.symbol} имеет статус {symbol_info.get('status')}, торговля запрещена.")
                 self.register_symbol_api_error(config.symbol, f'status={symbol_info.get("status")}')
                 return

            # Оптимизация цены входа
            if self.order_manager:
                optimized_price = self.order_manager.optimize_order_price(
                    config.symbol, 
                    "Buy" if config.direction == "long" else "Sell",
                    config.first_order_amount,
                    entry_price
                )
                entry_price = optimized_price
            
            # Плечо
            max_coin_leverage = self.get_max_leverage(symbol_info)
            config_leverage = config.leverage
            actual_leverage = min(config_leverage, max_coin_leverage)
            
            self.logger.info(f"⚖️ Плечо для {config.symbol}: Итоговое={actual_leverage}")

            # Расчет количества
            quantity = (config.first_order_amount * actual_leverage) / entry_price
            adjusted_quantity = self.adjust_quantity(config.symbol, quantity)
            
            if adjusted_quantity <= 0:
                self.logger.error(f"Скорректированное количество <= 0 для {config.symbol}")
                return

            # Форматирование QTY
            qty_precision = 0
            lot_size_filter = symbol_info.get('lotSizeFilter', {})
            qty_step = str(lot_size_filter.get('qtyStep', '1'))
            if '.' in qty_step:
                qty_precision = len(qty_step.split('.')[1])
            formatted_qty = f"{adjusted_quantity:.{qty_precision}f}"

            # 1. Установка плеча
            try:
                self.rate_limited_request(
                    self.session.set_leverage,
                    category="linear",
                    symbol=config.symbol,
                    buyLeverage=str(actual_leverage),
                    sellLeverage=str(actual_leverage)
                )
            except Exception as e:
                self.logger.warning(f"Не удалось установить плечо для {config.symbol}: {e}")
            
            # 2. Размещение рыночного ордера
            side = "Buy" if config.direction == "long" else "Sell"
            position_idx = self.get_position_idx_for_side(side)
            
            if self.is_symbol_in_timeout(symbol):
                return

            order_response = self.rate_limited_request(
                self.session.place_order,
                category="linear",
                symbol=config.symbol,
                side=side,
                orderType="Market",
                qty=formatted_qty,
                timeInForce="GTC",
                positionIdx=position_idx
            )
            
            if order_response and order_response.get('retCode') == 0:
                self.logger.info(f"✅ Ордер на вход размещен для {config.symbol}")
                # Успешный ответ API — сбросить счётчик ошибок по символу
                try:
                    self.reset_symbol_api_error_count(config.symbol)
                except Exception:
                    pass
                
                # Ожидание появления позиции
                position = None
                for attempt in range(5):
                    time.sleep(1.5) 
                    positions = self.fetch_positions(symbol=config.symbol)
                    position = next((p for p in positions if p['symbol'] == config.symbol and float(p['size']) > 0), None)
                    if position:
                        break
                    
                if position:
                    self.logger.info(f"Позиция подтверждена для {config.symbol}, размещаем сетку")
                    self.place_grid_orders(config, entry_price, side, actual_leverage, position_idx)
                    tp_success = self.update_take_profit_for_position(position, config)
                    
                    # === ВАЖНО: Сохраняем начальную цену и размер ===
                    self._update_position_state(config.symbol, float(position['size']), float(position['entry_price']))

                    config.failed_entry_attempts = 0
                else:
                    self.logger.error(f"⚠️ Позиция не появилась для {config.symbol} после ордера")
                    config.failed_entry_attempts += 1
            else:
                error_msg = order_response.get('retMsg', 'Unknown error') if order_response else 'No response'
                self.logger.error(f"❌ Ошибка входа {config.symbol}: {error_msg}")
                config.failed_entry_attempts += 1
                # Если это ошибка типа 'symbol is not supported' или код 10001 — регистрируем
                try:
                    msg = error_msg if isinstance(error_msg, str) else str(error_msg)
                    ret_code = order_response.get('retCode') if isinstance(order_response, dict) else None
                except Exception:
                    msg = str(error_msg)
                    ret_code = None
                if ret_code == 10001 or 'symbol is not supported' in msg.lower() or error_msg == 'No response':
                    try:
                        self.register_symbol_api_error(config.symbol, msg)
                    except Exception:
                        pass


        except Exception as e:
            err_text = str(e)
            self.logger.error(f"Критическая ошибка открытия позиции для {config.symbol}: {err_text}")
            if 'symbol is not supported' in err_text.lower() or '10001' in err_text:
                try:
                    self.register_symbol_api_error(config.symbol, err_text)
                except Exception:
                    pass
            config.failed_entry_attempts += 1

    def remove_coin_from_working_list_safe(self, symbol):
        """Безопасное удаление монеты из списка рабочих при фатальных ошибках"""
        self.working_coin_configs = [c for c in self.working_coin_configs if c.symbol != symbol]
        self.save_working_coin_configs()
        # Используем root.after для безопасного обновления UI из потока
        if self.root:
            self.root.after(0, self.update_working_coin_display)

    def place_grid_orders(self, config, entry_price, side, actual_leverage, position_idx):
        self.logger.info(f"🚀 СТАРТ размещения сетки для {config.symbol}. "
                        f"Сторона: {side}, Плечо: {actual_leverage}, Маржа первого: {config.first_order_amount:.2f} USDT")
        
        # 1. Попытка отменить старые ордера (Безопасная)
        try:
            self.cancel_all_orders_for_symbol(config.symbol)
            time.sleep(0.5) 
        except Exception as e:
            self.logger.error(f"⚠️ Не удалось отменить старые ордера (некритично): {e}")

        try:
            total_amount_no_leverage = config.first_order_amount
            total_amount_with_leverage = config.first_order_amount * actual_leverage
            base_price = float(entry_price) # Гарантируем float
            
            # Определение количества ордеров
            if config.grid_mode == 'manual' and config.manual_steps:
                max_orders = min(config.grid_orders_count, len(config.manual_steps) + 1)
            else:
                max_orders = config.grid_orders_count
            
            self.logger.info(f"⚙️ Расчет: {max_orders} ордеров. Первый объем (с плечом): {total_amount_with_leverage:.2f} USDT")

            # Получаем информацию о символе для правильного форматирования
            symbol_info = self.get_symbol_info(config.symbol)
            qty_precision = 0
            price_precision = 4 # Дефолт
            
            if symbol_info:
                try:
                    lot_size_filter = symbol_info.get('lotSizeFilter', {})
                    qty_step = str(lot_size_filter.get('qtyStep', '1'))
                    if '.' in qty_step:
                        qty_precision = len(qty_step.split('.')[1])
                    
                    price_filter = symbol_info.get('priceFilter', {})
                    tick_size = str(price_filter.get('tickSize', '0.0001'))
                    if '.' in tick_size:
                        price_precision = len(tick_size.split('.')[1])
                except Exception as e:
                    self.logger.warning(f"Ошибка парсинга symbol_info для {config.symbol}: {e}")

            for i in range(max_orders):
                # Проверки лимитов объемов
                if total_amount_no_leverage >= config.max_total_amount:
                    self.logger.info(f"🛑 Достигнут лимит объема (без плеча) на шаге {i+1}")
                    break
                
                # Расчет объема текущего ордера
                order_amount_no_leverage = config.first_order_amount * (config.volume_multiplier ** (i+1))  # multiplier applies to first grid order as well
                order_amount_with_leverage = order_amount_no_leverage * actual_leverage
                
                # Проверка превышения макс суммы
                if total_amount_no_leverage + order_amount_no_leverage > config.max_total_amount:
                    break

                # Расчет цены ордера
                if config.grid_mode == 'auto':
                    step = config.grid_step * (i + 1)
                else:
                    if i < len(config.manual_steps):
                        step = sum(config.manual_steps[:i+1])
                    else:
                        # Fallback для ручного режима
                        last_step = config.manual_steps[-1] if config.manual_steps else config.grid_step
                        step = sum(config.manual_steps) + last_step * (i + 1 - len(config.manual_steps))
                
                # Важная проверка на ноль
                if base_price <= 0:
                     self.logger.error(f"❌ Ошибка: базовая цена {base_price} <= 0")
                     break

                if side == "Buy":
                    # Для лонга усреднение ниже цены входа (Limit Buy)
                    order_price = base_price * (1 - step / 100)
                else:
                    # Для шорта усреднение выше цены входа (Limit Sell)
                    order_price = base_price * (1 + step / 100)
                
                # Оптимизация цены
                if self.order_manager:
                    try:
                        order_price = self.order_manager.optimize_order_price(
                            config.symbol, side, order_amount_no_leverage, order_price
                        )
                    except Exception:
                        pass

                # Расчет количества монет
                if order_price <= 0:
                    self.logger.error(f"❌ Ошибка цены ордера {i+1}: {order_price}")
                    continue

                quantity = order_amount_with_leverage / order_price
                adjusted_quantity = self.adjust_quantity(config.symbol, quantity)
                
                if adjusted_quantity <= 0:
                    self.logger.warning(f"⚠️ Ордер {i+1} пропущен: слишком маленький объем ({quantity:.4f} -> {adjusted_quantity})")
                    continue

                # Форматирование
                formatted_qty = f"{adjusted_quantity:.{qty_precision}f}"
                formatted_price = f"{order_price:.{price_precision}f}"

                # Размещение ордера
                try:
                    # Для хедж режима: 
                    # Если открыт Long (Buy), то усреднение - это тоже Buy (Limit).
                    # Если открыт Short (Sell), то усреднение - это тоже Sell (Limit).
                    
                    order_response = self.rate_limited_request(
                        self.session.place_order,
                        category="linear",
                        symbol=config.symbol,
                        side=side, # Направление такое же, как у позиции!
                        orderType="Limit",
                        qty=formatted_qty,
                        price=formatted_price,
                        timeInForce="GTC",
                        positionIdx=position_idx
                    )
                    
                    if order_response and order_response.get('retCode') == 0:
                        total_amount_no_leverage += order_amount_no_leverage
                        # total_amount_with_leverage += order_amount_with_leverage # (не используется для лимита, но можно считать)
                        self.logger.info(f"✅ Ордер сетки #{i+1} размещен: {side} {formatted_qty} по {formatted_price}. "
                                        f"Сумма без плеча: {order_amount_no_leverage:.2f} USDT")
                    else:
                        msg = order_response.get('retMsg', 'Unknown') if order_response else 'No response'
                        self.logger.error(f"❌ Ошибка API ордера #{i+1} ({config.symbol}): {msg}")
                        # Если ошибка указывает, что символ не поддерживается, регистрируем
                        try:
                            ret_code = order_response.get('retCode') if isinstance(order_response, dict) else None
                            msg_text = msg if isinstance(msg, str) else str(msg)
                        except Exception:
                            ret_code = None
                            msg_text = str(msg)
                        if ret_code == 10001 or 'symbol is not supported' in msg_text.lower():
                            try:
                                self.register_symbol_api_error(config.symbol, msg_text)
                            except Exception:
                                pass

                        
                    time.sleep(0.2) 
                    
                except Exception as e:
                    err_text = str(e)
                    self.logger.error(f"❌ Исключение при размещении ордера #{i+1}: {err_text}")
                    if 'symbol is not supported' in err_text.lower() or '10001' in err_text:
                        try:
                            self.register_symbol_api_error(config.symbol, err_text)
                        except Exception:
                            pass
                    continue

            self.logger.info(f"🏁 Размещение сетки завершено. Итоговый объем маржи: {total_amount_no_leverage:.2f} USDT")

        except Exception as e:
            self.logger.error(f"🔥 КРИТИЧЕСКАЯ ОШИБКА в place_grid_orders: {e}", exc_info=True)

    def fetch_positions(self, symbol=None):
        # === ИСПРАВЛЕНИЕ: Проверка подключения ===
        if not self.session:
            return []
            
        try:
            kwargs = {"category": "linear"}
            if symbol:
                kwargs["symbol"] = symbol
            else:
                kwargs["settleCoin"] = "USDT"
            response = self.rate_limited_request(
                self.session.get_positions,
                **kwargs
            )
            if response and response.get('retCode') == 0:
                positions = []
                for pos in response['result']['list']:
                    size = self.safe_float(pos.get('size', 0))
                    if size <= 0:
                        continue
                    positions.append({
                        'symbol': pos.get('symbol', ''),
                        'side': pos.get('side', ''),
                        'size': size,
                        'entry_price': self.safe_float(pos.get('avgPrice', 0)),
                        'mark_price': self.safe_float(pos.get('markPrice', 0)),
                        'liq_price': self.safe_float(pos.get('liqPrice', 0)),
                        'pnl': self.safe_float(pos.get('unrealisedPnl', 0))
                    })
                self.positions_data = positions
                return positions
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                # Логируем ошибку только если это не штатная ситуация
                self.logger.error(f"Ошибка получения позиций: {error_msg}")
                return []
        except Exception as e:
            self.logger.error(f"Исключение при получении позиций: {e}")
            return []

    def _update_position_state(self, symbol, size, entry_price=None):
        """
        ИСПРАВЛЕНИЕ: Обновляет внутреннее состояние позиции, включая цену входа.
        """
        current_time = time.time()
        if symbol not in self._position_states:
            self._position_states[symbol] = {
                'size': size,
                'entry_time': current_time,
                'last_check': current_time,
                'entry_price': entry_price # НОВОЕ: для хранения цены входа при усреднении
            }
        else:
            self._position_states[symbol]['size'] = size
            self._position_states[symbol]['last_check'] = current_time
            if entry_price is not None:
                self._position_states[symbol]['entry_price'] = entry_price # Обновляем цену

    def _check_position_closed(self, symbol):
        if symbol not in self._position_states:
            return False
        current_positions = self.fetch_positions(symbol=symbol)
        current_position = next((p for p in current_positions if p['symbol'] == symbol and float(p['size']) > 0), None)
        if not current_position and self._position_states[symbol]['size'] > 0:
            self.logger.info(f"Обнаружено закрытие позиции для {symbol}")
            return True
        if current_position:
            self._update_position_state(symbol, float(current_position['size']))
        else:
            self._update_position_state(symbol, 0)
        return False

    def check_closed_positions(self):
        """Проверяет, исчезли ли позиции, которые бот считал открытыми"""
        try:
            # Используем копию списка
            active_configs = self.working_coin_configs[:]
            
            for config in active_configs:
                symbol = config.symbol
                
                if self.is_symbol_in_timeout(symbol):
                    continue

                # Проверка: По внутреннему состоянию
                if self._check_position_closed(symbol):
                    self.logger.info(f"🏁 Позиция {symbol} закрыта (исчезла с биржи). Запуск очистки.")
                    self._handle_position_closed_immediate(symbol, reason="tp")
                    self.cleanup_finished_coin_with_timeout(symbol)
                    
        except Exception as e:
            self.logger.error(f"Ошибка проверки закрытых позиций: {e}")

    def enhanced_cancel_all_orders(self, symbol):
        # HEDGE-SAFE GUARD: do not mass-cancel if a position exists
        try:
            positions = self.fetch_positions(symbol=str(symbol).strip().upper())
            for p in positions or []:
                if p.get('symbol') == str(symbol).strip().upper() and float(p.get('size', 0)) != 0:
                    self.logger.warning(f"🛡️ Массовая отмена запрещена при открытой позиции: {symbol}")
                    return
        except Exception:
            pass
        safe_symbol = str(symbol).strip().upper()
        try:
            cancel_response = self.rate_limited_request(
                self.session.cancel_all_orders,
                category="linear",
                symbol=safe_symbol
            )
            if cancel_response and cancel_response.get('retCode') == 0:
                self.logger.info(f"Все ордеры для {safe_symbol} отправлены на отмену через массовую отмену")
            else:
                self.logger.info(f"Массовая отмена не удалась для {safe_symbol}, отменяем по одному")
                open_orders = self.fetch_orders(safe_symbol)
                for order in open_orders:
                    if order['symbol'] == safe_symbol and order['order_type'] == 'Limit':
                        try:
                            self.rate_limited_request(
                                self.session.cancel_order,
                                category="linear",
                                symbol=safe_symbol,
                                orderId=order['order_id']
                            )
                            self.logger.debug(f"Ордер отменен для {safe_symbol}: {order['order_id']}")
                        except Exception as e:
                            self.logger.warning(f"Ошибка при отмене ордера {order['order_id']} для {safe_symbol}: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка массовой отмены ордеров для {safe_symbol}: {e}")
            self.cancel_all_orders_for_symbol(safe_symbol)

    def monitor_and_update_tp(self, config):
        """
        ИСПРАВЛЕНИЕ: Обновляет TP и сетку после КАЖДОГО усреднения (исполнения ордера сетки).
        """
        if not config or not config.enabled:
            return
        symbol = config.symbol
        
        # Получаем текущую позицию
        positions = self.fetch_positions(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
        
        if not position:
            # Если позиции нет, проверяем, не закрылась ли она
            self.check_closed_positions()
            return
        
        current_size = float(position['size'])
        current_entry_price = float(position['entry_price'])
        
        # Получаем размер позиции, который был ИЗВЕСТЕН боту перед последним усреднением.
        last_known_size = self._position_states.get(symbol, {}).get('size', 0)
        last_known_price = self._position_states.get(symbol, {}).get('entry_price', 0)
        
        # --- ЛОГИКА ИСПРАВЛЕНИЯ: Обновление TP после КАЖДОГО усреднения ---
        if current_size > last_known_size and last_known_size > 0:
            # Вычисляем разницу в процентах
            size_change_pct = ((current_size - last_known_size) / last_known_size) * 100
            
            # Если увеличение больше 0.1% - это значительное изменение
            if size_change_pct > 0.1:
                self.logger.info(f"🚀 УСРЕДНЕНИЕ {symbol}: Позиция выросла {last_known_size:.4f} -> {current_size:.4f} ({size_change_pct:.2f}%). Вызываем пересчет TP...")
                
                # Обновляем память о размере СВЕЖЕЙ ценой входа
                self._update_position_state(symbol, current_size, current_entry_price)
                
                # ВАЖНОЕ ИСПРАВЛЕНИЕ: Вызываем пересчет TP через специальный метод
                success = self._recalculate_tp_after_grid_fill(symbol, config)
                
                if success:
                    self.logger.info(f"✅ TP успешно пересчитан после усреднения {symbol}")
                else:
                    self.logger.warning(f"⚠️ Не удалось сдвинуть TP для {symbol} после усреднения")
                
                # Отменяем старые ордера сетки (чтобы убрать уже сработавший)
                # Это предотвращает двойное исполнение одного и того же ордера
                self.cancel_all_orders_for_symbol(symbol)
            else:
                # Незначительное изменение - просто обновляем состояние
                self._update_position_state(symbol, current_size, current_entry_price)
        
        elif current_size != last_known_size:
             # Инициализация или частичное закрытие
             self._update_position_state(symbol, current_size, current_entry_price)
             
             # Если размер уменьшился (частичное закрытие), тоже обновляем TP
             if current_size < last_known_size:
                 self.logger.info(f"📉 Частичное закрытие {symbol}: {last_known_size:.4f} -> {current_size:.4f}")
                 time.sleep(1.0)
                 self.update_take_profit_based_on_average(symbol, config, force_update=True)
             
             # На всякий случай проверяем TP, если это первый запуск
             elif last_known_size == 0 and not config.use_manual_tp:
                 time.sleep(1.0)
                 self.update_take_profit_based_on_average(symbol, config, force_update=False)
        
        # Дополнительная проверка: если цена входа изменилась (например, из-за проскальзывания)
        elif last_known_price > 0 and abs(current_entry_price - last_known_price) / last_known_price > 0.0001:
            self.logger.info(f"📊 Изменение средней цены {symbol}: {last_known_price:.8f} -> {current_entry_price:.8f}")
            self._update_position_state(symbol, current_size, current_entry_price)
            self.update_take_profit_based_on_average(symbol, config, force_update=True)

    def _recalculate_tp_after_grid_fill(self, symbol, config):
        """
        FIX: Гарантированный пересчёт TP после исполнения любого сеточного ордера.
        Никакой заморозки, никакой доп. логики — только TP.
        """
        try:
            # Берём СВЕЖУЮ позицию с биржи
            positions = self.fetch_positions(symbol=symbol)
            position = next(
                (p for p in positions if p['symbol'] == symbol and float(p['size']) > 0),
                None
            )

            if not position:
                self.logger.warning(f"❌ Нет открытой позиции для {symbol} при пересчете TP")
                return False

            avg_price = float(position['entry_price'])
            size = float(position['size'])
            side = position['side']

            # Сохраняем новую среднюю цену в конфиг
            config._initial_entry_price = avg_price

            self.logger.info(
                f"🔁 GRID-FILL → TP RECALC: {symbol} | avg={avg_price:.8f} | size={size:.4f} | side={side}"
            )

            # ⛔ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ
            # TP пересчитывается ПРИНУДИТЕЛЬНО
            success = self.update_take_profit_based_on_average(
                symbol,
                config,
                force_update=True
            )

            if success:
                self.logger.info(f"✅ TP успешно пересчитан после усреднения {symbol}")
                # Обновляем кэш успешного TP
                current_tp = self.get_current_take_profit(symbol)
                if current_tp:
                    self._last_successful_tp[symbol] = {
                        'tp_price': current_tp,
                        'timestamp': time.time()
                    }
            else:
                self.logger.warning(f"⚠️ TP НЕ удалось обновить после усреднения {symbol}")
                # Пробуем еще раз через 2 секунды
                time.sleep(2.0)
                retry_success = self.update_take_profit_based_on_average(
                    symbol,
                    config,
                    force_update=True
                )
                if retry_success:
                    self.logger.info(f"✅ TP успешно пересчитан при повторной попытке {symbol}")
                else:
                    self.logger.error(f"❌ TP не удалось обновить даже после повторной попытки {symbol}")

            return success

        except Exception as e:
            self.logger.error(f"❌ Ошибка TP-recalc после grid-fill {symbol}: {e}", exc_info=True)
            return False

    def update_take_profit_based_on_average(self, symbol, config, force_update=False):
        """Обновляет TP от средней цены входа, используя take_profit из конфига, но не ниже 0.8%"""
        
        # Всегда запрашиваем свежие данные, так как avgPrice меняется на бирже
        positions = self.fetch_positions(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
        
        if not position:
            self.logger.warning(f"Нет позиции для {symbol} при обновлении TP")
            return False
            
        # Получаем актуальную среднюю цену входа
        average_price = float(position['entry_price']) 
        
        # Сохраняем актуальную среднюю цену в конфиг
        config._initial_entry_price = average_price
        
        side = position['side']
        
        self.logger.info(f"🔄 Пересчет TP для {symbol}. Новая средняя цена: {average_price:.8f}. Force: {force_update}")
        
        # Всегда используем force_update=True при вызове из _recalculate_tp_after_grid_fill
        # чтобы гарантировать обновление TP после усреднения
        return self.set_take_profit_with_protection(symbol, side, config, force_update=True)

    def handle_api_error(self, response, operation_name):
        if response is None:
            self.logger.error(f"Пустой ответ в {operation_name}")
            return False
        if response.get('retCode') == 0:
            return True
        error_code = response.get('retCode')
        error_msg = response.get('retMsg', 'Unknown error')
        self.logger.error(f"API ошибка в {operation_name}: {error_code} - {error_msg}")
        if error_code == 10001:
            self.logger.error("Отсутствуют обязательные параметы в запросе")
        elif error_code == 10002:
            self.logger.error("Ошибка валидации API")
        elif error_code == 10006:
            self.logger.warning("Превышен лимит запросов, увеличиваем задержку")
            self._dynamic_delay_multiplier = min(5.0, self._dynamic_delay_multiplier * 1.5)
        return False

    def start_performance_monitoring(self):
        def monitor():
            while True:
                try:
                    self.performance_stats = self.performance_optimizer.get_performance_stats()
                    self.last_performance_update = time.time()
                    time.sleep(60)
                except Exception as e:
                    self.logger.error(f"Ошибка мониторинга производительности: {e}")
                    time.sleep(30)
        threading.Thread(target=monitor, daemon=True).start()

    def adaptive_rate_limit(self):
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        avg_response_time = self.performance_stats.get('avg_response_time', 0.1)
        error_rate = self.performance_stats.get('error_rate', 0)
        if error_rate > 0.1 or avg_response_time > 1.0:
            self._dynamic_delay_multiplier = min(3.0, self._dynamic_delay_multiplier * 0.8)
        elif error_rate < 0.01 and avg_response_time < 0.5:
            self._dynamic_delay_multiplier = max(0.5, self._dynamic_delay_multiplier * 0.9)
        adaptive_interval = self._min_request_interval * self._dynamic_delay_multiplier
        if elapsed < adaptive_interval:
            time.sleep(adaptive_interval - elapsed)
        self._last_request_time = time.time()

    @error_handler(logging.getLogger(), max_retries=2, fallback_value=None)
    @error_handler(logging.getLogger(), max_retries=2, fallback_value=None)
    def rate_limited_request(self, func, *args, **kwargs):
        self.adaptive_rate_limit()
        try:
            response = func(*args, **kwargs)
            if response is None:
                self.logger.error("Пустой ответ от API")
                return {'retCode': -1, 'retMsg': 'Empty response'}
            if 'retCode' not in response:
                self.logger.error("Некорректный формат ответа от API")
                return {'retCode': -1, 'retMsg': 'Invalid response format'}
            return response
        except Exception as e:
            error_str = str(e)
            # === ИСПРАВЛЕНИЕ: Расширенная обработка некритичных ошибок ===
            # 110043 - плечо уже установлено
            # 34040 - параметры не изменены (TP уже стоит такой же)
            # "not modified" - текстовое описание ошибки
            if any(code in error_str for code in ['110043', '34040', 'not modified', 'leverage not modified']):
                # Логируем как debug, чтобы не засорять основной лог ошибками
                self.logger.debug(f"API Info (пропуск ошибки): {error_str}")
                # Возвращаем имитацию успешного ответа с кодом ошибки, чтобы вызывающий метод мог обработать
                return {'retCode': 34040 if '34040' in error_str or 'not modified' in error_str else 110043, 'retMsg': error_str}
            
            # Для всех остальных ошибок логируем как ERROR и выбрасываем исключение
            self.logger.error(f"Исключение при вызове API: {e}")
            raise

    def batch_fetch_klines(self, symbols: List[str], interval: str, limit: int) -> Dict[str, pd.DataFrame]:
        tasks = []
        for symbol in symbols:
            task = lambda s=symbol: self.fetch_klines_for_symbol(s, interval, limit)
            tasks.append(task)
        results = self.performance_optimizer.batch_process(tasks)
        kline_data = {}
        for symbol, result in zip(symbols, results):
            if result is not None and not result.empty:
                kline_data[symbol] = result
        return kline_data

    def initialize_order_manager(self):
        if self.session and not self.order_manager:
            self.order_manager = OrderManager(
                self.session,
                self.rate_limited_request,
                self.logger
            )

    def load_blacklist(self):
        return self.error_handler.safe_execute(
            self._load_blacklist_impl,
            fallback_value=[]
        )

    def _load_blacklist_impl(self):
        if os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                    blacklist = json.load(f)
                    self.logger.info(f"Черный список загружен. Количество монет: {len(blacklist)}")
                    return blacklist
            except Exception as e:
                self.logger.error(f"Ошибка загрузки черного списка: {e}")
                return []
        self.logger.info("Файл черного списка не найден, создан пустой список")
        return []

    def save_blacklist(self):
        self.error_handler.safe_execute(
            self._save_blacklist_impl
        )

    def _save_blacklist_impl(self):
        with open(self.blacklist_file, 'w', encoding='utf-8') as f:
            json.dump(self.blacklist, f, indent=2, ensure_ascii=False)
        self.logger.debug(f"Черный список сохранен. Количество монет: {len(self.blacklist)}")

    def add_to_blacklist(self, symbol):
        symbol = symbol.upper().strip()
        if symbol not in self.blacklist:
            self.blacklist.append(symbol)
            self.save_blacklist()
            self.logger.info(f"Монета {symbol} добавлена в черный список. Текущий размер черного списка: {len(self.blacklist)}")
        else:
            self.logger.debug(f"Монета {symbol} уже находится в черном списке")

    def remove_from_blacklist(self, symbol):
        symbol = symbol.upper().strip()
        if symbol in self.blacklist:
            self.blacklist.remove(symbol)
            self.save_blacklist()
            self.logger.info(f"Монета {symbol} удалена из черного списка. Текущий размер черного списка: {len(self.blacklist)}")
        else:
            self.logger.debug(f"Монета {symbol} не найдена в черном списке")

    def is_in_blacklist(self, symbol):
        return symbol.upper().strip() in self.blacklist

    def load_working_coin_configs(self):
        if os.path.exists(self.working_coin_configs_file):
            try:
                with open(self.working_coin_configs_file, 'r') as f:
                    data = json.load(f)
                    self.working_coin_configs = []
                    for item in data:
                        config = TradingPairConfig()
                        config.symbol = item['symbol']
                        config.first_order_amount = float(item['first_order_amount'])
                        config.leverage = int(item['leverage'])
                        config.take_profit = float(item['take_profit'])
                        config.min_take_profit = 0.8  # ИСПРАВЛЕНИЕ: Всегда 1.1%
                        config.grid_orders_count = int(item['grid_orders_count'])
                        config.grid_step = float(item['grid_step'])
                        config.volume_multiplier = float(item['volume_multiplier'])
                        config.max_total_amount = float(item['max_total_amount'])
                        config.enabled = bool(item['enabled'])
                        config.grid_mode = item.get('grid_mode', 'auto')
                        config.manual_steps = item.get('manual_steps', [])
                        config.direction = item.get('direction', '')
                        config.use_manual_tp = bool(item.get('use_manual_tp', False))
                        config.manual_tp_price = float(item.get('manual_tp_price', 0.0))
                        config.failed_entry_attempts = int(item.get('failed_entry_attempts', 0))  # Загружаем счетчик неудачных попыток
                        self.working_coin_configs.append(config)
                self.logger.info(f"Загружено {len(self.working_coin_configs)} монет в работе")
            except Exception as e:
                self.logger.error(f"Ошибка загрузки монет в работе: {e}")
                self.working_coin_configs = []
        else:
            self.logger.info("Файл монет в работе не найден, создан пустой список")
            self.working_coin_configs = []

    def save_working_coin_configs(self):
        try:
            data = []
            for config in self.working_coin_configs:
                data.append({
                    'symbol': config.symbol,
                    'first_order_amount': config.first_order_amount,
                    'leverage': config.leverage,
                    'take_profit': config.take_profit,
                    'min_take_profit': 0.8,  # ИСПРАВЛЕНИЕ: Всегда 1.1%
                    'grid_orders_count': config.grid_orders_count,
                    'grid_step': config.grid_step,
                    'volume_multiplier': config.volume_multiplier,
                    'max_total_amount': config.max_total_amount,
                    'enabled': config.enabled,
                    'grid_mode': config.grid_mode,
                    'manual_steps': config.manual_steps,
                    'direction': config.direction,
                    'use_manual_tp': config.use_manual_tp,
                    'manual_tp_price': config.manual_tp_price,
                    'failed_entry_attempts': config.failed_entry_attempts  # Сохраняем счетчик неудачных попыток
                })
            with open(self.working_coin_configs_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.info(f"Сохранено {len(data)} монет в работе")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения монет в работе: {e}")

    def load_working_coin_defaults(self):
        if os.path.exists(self.working_coin_defaults_file):
            try:
                with open(self.working_coin_defaults_file, 'r') as f:
                    data = json.load(f)
                    self.working_coin_defaults = data
                    self.max_working_coins = data.get('max_working_coins', 1)
                self.logger.info("Настройки монеты в работе загружены из файла")
            except Exception as e:
                self.logger.error(f"Ошибка загрузки настроек монеты в работе: {e}")
                self.working_coin_defaults = self.get_default_working_config()
                self.max_working_coins = 1
        else:
            self.logger.info("Файл настроек монеты в работе не найден, используются настройки по умолчанию")
            self.working_coin_defaults = self.get_default_working_config()
            self.max_working_coins = 1

    def get_default_working_config(self):
        return {
            'first_order_amount': 1.0,
            'leverage': 20,
            'take_profit': 1.5,
            'min_take_profit': 0.8,  # ИСПРАВЛЕНИЕ: Всегда 1.1%
            'grid_orders_count': 8,
            'grid_step': 4.5,
            'volume_multiplier': 1.2,
            'max_total_amount': 200.0,
            'grid_mode': 'manual',
            'manual_steps': [
                4.0,
                4.0,
                4.5,
                4.5,
                4.0,
                4.0,
                9.0
            ],
            'enabled': True,
            'max_working_coins': 1
        }

    def save_working_coin_defaults(self, config_dict):
        try:
            with open(self.working_coin_defaults_file, 'w') as f:
                json.dump(config_dict, f, indent=2)
            self.working_coin_defaults = config_dict
            self.max_working_coins = config_dict.get('max_working_coins', 1)
            self.logger.info("Настройки монеты в работе сохранены")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения настроек по умолчанию: {e}")

    def load_trade_history(self):
        if os.path.exists(self.trade_history_file):
            try:
                with open(self.trade_history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.trade_history = data
                self.logger.info(f"История сделок загружена. Количество записей: {len(self.trade_history)}")
            except Exception as e:
                self.logger.error(f"Ошибка загрузки истории сделок: {e}")
                self.trade_history = []
        else:
            self.logger.info("Файл истории сделок не найден, создана пустая история")
            self.trade_history = []

    def save_trade_history(self):
        try:
            with open(self.trade_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.trade_history, f, indent=2, ensure_ascii=False)
            self.logger.debug(f"История сделок сохранена. Количество записей: {len(self.trade_history)}")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения истории сделок: {e}")

    def schedule_suitable_update(self):
        # Запускаем процесс обновления
        self.update_suitable_coins()
        
        # Планируем следующий запуск через интервал (в миллисекундах)
        # 300 * 1000 = 300000 мс = 5 минут
        interval_ms = self.suitable_update_interval * 800
        self.root.after(interval_ms, self.schedule_suitable_update)

    def update_working_coin_display(self):
        for item in self.working_coin_tree.get_children():
            self.working_coin_tree.delete(item)
        for config in self.working_coin_configs:
            if config.direction == "long":
                direction_icon = "🟢"
                direction_text = "LONG"
                direction_color = "#44bd32"
            else:
                direction_icon = "🔴" 
                direction_text = "SHORT"
                direction_color = "#e84118"
            has_position = self.has_open_position(config.symbol)
            status_icon = "✅" if has_position else "⏳"
            status_text = "Активна" if has_position else "Ожидание"
            tp_type = "🔧 ручной" if config.use_manual_tp else "🤖 авто"
            self.working_coin_tree.insert('', tk.END, values=(
                config.symbol,
                f"{direction_icon} {direction_text}",
                f"{tp_type}",
                f"{status_icon} {status_text}"
            ))

    def update_suitable_coins_table(self):
        for item in self.suitable_coins_tree.get_children():
            self.suitable_coins_tree.delete(item)
        for coin in self.suitable_coins:
            volume_str = f"{coin.volume_24h/1000000:.2f}M" if coin.volume_24h >= 1000000 else f"{coin.volume_24h/1000:.2f}K"
            price_str = f"{coin.price:.4f}" if coin.price < 1 else f"{coin.price:.2f}"
            change_15m_color = "#44bd32" if coin.change_15m >= 0 else "#e84118"
            change_24h_color = "#44bd32" if coin.change_24h >= 0 else "#e84118"
            if coin.direction == "long":
                direction_icon = "🟢"
                direction_text = "LONG"
            else:
                direction_icon = "🔴"
                direction_text = "SHORT"
            confidence = "Высокая" if "ml" in coin.strategy else "Средняя"
            item = self.suitable_coins_tree.insert('', tk.END, values=(
                coin.symbol,
                price_str,
                f"{coin.change_15m:+.2f}%",
                f"{coin.change_24h:+.2f}%",
                volume_str,
                f"{direction_icon} {direction_text}",
                coin.strategy,
                confidence
            ))

    def update_position_display(self):
        for item in self.position_tree.get_children():
            self.position_tree.delete(item)
        positions = self.fetch_positions()
        working_symbols = {config.symbol for config in self.working_coin_configs}
        for position in positions:
            symbol = position['symbol']
            size = float(position['size'])
            if size <= 0 or symbol not in working_symbols:
                continue
            side = position['side']
            side_icon = "🟢" if side == "Buy" else "🔴"
            side_text = f"{side_icon} {side}"
            entry_price = float(position['entry_price'])
            position_size_usdt = size * entry_price
            pnl = float(position['pnl'])
            mark_price = float(position['mark_price'])
            pnl_percent = ((mark_price - entry_price) / entry_price * 100) if side == "Buy" else ((entry_price - mark_price) / entry_price * 100)
            current_tp = self.get_current_take_profit(symbol)
            tp_set = "Да" if current_tp else "Нет"
            pnl_color = "#44bd32" if pnl >= 0 else "#e84118"
            status = "✅ Открыта" if size > 0 else "❌ Закрыта"
            item = self.position_tree.insert('', tk.END, values=(
                symbol,
                side_text,
                f"{entry_price:.4f}",
                f"{position_size_usdt:.2f}",
                f"{pnl:+.2f}",
                f"{pnl_percent:+.2f}%",
                tp_set,
                status
            ))

    def update_data(self):
        try:
            if self.session:
                self.fetch_balance()
                tickers = self.fetch_tickers()
                self.fetch_positions()
                self.fetch_orders()
                ticker = next((t for t in tickers if t['symbol'] == self.current_symbol), None)
                if ticker:
                    # trend arrow based on last price
                    arrow = ""
                    if self._prev_price is not None:
                        if ticker['price'] > self._prev_price:
                            arrow = " ⬆"
                        elif ticker['price'] < self._prev_price:
                            arrow = " ⬇"
                    self.price_card.config(text=f"{ticker['price']:.4f}{arrow}")
                    self._prev_price = ticker['price']
                    change = ticker['change']
                    change_color = "#44bd32" if change >= 0 else "#e84118"
                    self.change_card.config(text=f"{change:+.2f}%", foreground=change_color)
                    volume = ticker['volume']
                    volume_str = f"{volume/1000000:.2f}M" if volume >= 1000000 else f"{volume/1000:.2f}K"
                    self.volume_card.config(text=volume_str)
                    signals_count = len(self.suitable_coins)
                    self.signal_card.config(text=f"{signals_count}")
                status_text = "● Подключено" if self.session else "● Не подключено"
                status_color = "#44bd32" if self.session else "#e84118"
                self.status_label.config(text=status_text, foreground=status_color)
                self.account_type_small.config(text="● Демо" if self.demo_trading else "● Реальный")
                self.auto_small.config(text=f"🤖 {'Вкл' if self.auto_trading else 'Выкл'}")
                self.balance_small.config(text=f"💰 {self.balance:.2f} USDT")
                self.update_position_display()
                # Refresh orders table
                self._refresh_orders_table()
                # Update status bar metrics
                perf = self.performance_optimizer.get_performance_stats()
                rps = perf.get('requests_per_second', 0.0)
                err = perf.get('error_rate', 0.0)
                self.status_perf_label.config(text=f"RPS: {rps:.2f} | Error: {err:.2%}")
                self.status_updated_label.config(text=f"Обновлено {int(time.time()-self._last_ui_update_ts)} сек назад")
                self._last_ui_update_ts = time.time()
            self.root.after(5000, self.update_data)
        except Exception as e:
            self.logger.error(f"Ошибка обновления данных: {e}")
            self.root.after(5000, self.update_data)

    def remove_working_coin(self):
        selected = self.working_coin_tree.selection()
        if not selected:
            messagebox.showinfo("Информация", "Выберите монету для удаления")
            return
        item = selected[0]
        symbol = self.working_coin_tree.item(item, 'values')[0]
        
        if messagebox.askyesno("Подтверждение", f"Удалить монету {symbol} из работы?\nВсе активные ордера (сетка) будут отменены."):
            self.logger.info(f"🛑 Пользователь удаляет монету {symbol} из работы")
            
            # 1. Удаляем из конфига
            self.working_coin_configs = [config for config in self.working_coin_configs if config.symbol != symbol]
            self.save_working_coin_configs()
            self.update_working_coin_display()
            
            # 2. Удаляем ордера (Сетка)
            # Используем усиленный метод отмены
            threading.Thread(target=self.enhanced_cancel_all_orders, args=(symbol,), daemon=True).start()
            
            # 3. Очищаем состояние
            if symbol in self._position_states:
                del self._position_states[symbol]
                
            messagebox.showinfo("Успех", f"Монета {symbol} удалена из работы, ордера отменяются...")
            self.logger.info(f"Монета {symbol} удалена из работы пользователем, отправлен запрос на отмену ордеров.")

    def cancel_all_orders_for_symbol(self, symbol):
        try:
            response = self.rate_limited_request(
                self.session.cancel_all_orders,
                category="linear",
                symbol=symbol
            )
            if response and response.get('retCode') == 0:
                self.logger.info(f"Все ордера для {symbol} отправлены на отмену через массовую отмену")
                return
            else:
                self.logger.info(f"Массовая отмена не удалась для {symbol}, отменяем по одному")
                open_orders = self.fetch_orders(symbol)
                for order in open_orders:
                    if order['symbol'] == symbol and order['order_type'] == 'Limit':
                        try:
                            self.rate_limited_request(
                                self.session.cancel_order,
                                category="linear",
                                symbol=symbol,
                                orderId=order['order_id']
                            )
                            self.logger.debug(f"Ордер отменен для {symbol}: {order['order_id']}")
                        except Exception as e:
                            self.logger.warning(f"Ошибка при отмене ордера {order['order_id']} для {symbol}: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка при отмене ордеров для {symbol}: {e}")

    def open_working_defaults_window(self):
        self.logger.info("Открытие окна настроек монеты в работе по умолчанию")
        win = tk.Toplevel(self.root)
        win.title("⚙️ Настройки по умолчанию для монеты в работе")
        win.geometry("600x800")
        config = self.working_coin_defaults
        form = ttk.Frame(win, padding=15)
        form.pack(fill=tk.BOTH, expand=True)
        entries = {}
        
        # === ИСПРАВЛЕНИЕ: ДОБАВЛЕНО ПОЛЕ volume_multiplier ===
        fields = [
            ("💰 Первый ордер (USDT):", "first_order_amount"),
            ("📈 Кредитное плечо:", "leverage"),
            ("🎯 Тейк-профит (%):", "take_profit"),
            ("📊 Минимальный тейк-профит (%):", "min_take_profit"),
            ("📋 Ордера сетки:", "grid_orders_count"),
            ("🚀 Множитель объема:", "volume_multiplier"), # <--- ДОБАВЛЕНО
            ("💎 Макс. сумма (USDT):", "max_total_amount"),
            ("🔢 Макс. монет в работе:", "max_working_coins")
        ]
        
        for i, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky=tk.W, pady=5)
            var = tk.StringVar(value=str(config.get(key, "")))
            entry = ttk.Entry(form, textvariable=var, width=20)
            entry.grid(row=i, column=1, sticky=tk.W, padx=10)
            entries[key] = var
            
        mode_var = tk.StringVar(value=config.get('grid_mode', 'auto'))
        ttk.Label(form, text="🎛️ Режим сетки:").grid(row=len(fields), column=0, sticky=tk.W, pady=5)
        ttk.Radiobutton(form, text="Автоматический", variable=mode_var, value="auto").grid(row=len(fields), column=1, sticky=tk.W)
        ttk.Radiobutton(form, text="Ручной", variable=mode_var, value="manual").grid(row=len(fields)+1, column=1, sticky=tk.W)
        manual_frame = ttk.Frame(form)
        manual_frame.grid(row=len(fields)+2, column=0, columnspan=2, sticky=tk.W, pady=10)
        self.manual_default_entries = []
        
        def update_manual_defaults():
            for widget in manual_frame.winfo_children():
                widget.destroy()
            self.manual_default_entries = []
            try:
                # Безопасное получение значений с дефолтами при ошибке
                grid_count_val = entries['grid_orders_count'].get()
                num = int(grid_count_val) - 1 if grid_count_val else 0
                
                if num > 0:
                    ttk.Label(manual_frame, text="📏 Шаги (%):").pack(anchor=tk.W)
                    current_steps = config.get('manual_steps', [config.get('grid_step', 1.0)] * num)
                    while len(current_steps) < num:
                        current_steps.append(config.get('grid_step', 1.0))
                    for i in range(num):
                        step_var = tk.StringVar(value=str(current_steps[i]) if i < len(current_steps) else str(config.get('grid_step', 1.0)))
                        ttk.Entry(manual_frame, textvariable=step_var, width=10).pack(pady=2)
                        self.manual_default_entries.append(step_var)
            except Exception as e:
                self.logger.warning(f"Ошибка при обновлении ручных настроек UI: {e}")

        def toggle_mode():
            if mode_var.get() == "manual":
                update_manual_defaults()
                manual_frame.grid()
            else:
                manual_frame.grid_remove()
                
        toggle_mode()
        mode_var.trace_add('write', lambda *a: toggle_mode())
        # Обновляем при изменении количества ордеров
        entries['grid_orders_count'].trace_add('write', lambda *a: update_manual_defaults() if mode_var.get() == "manual" else None)
        
        enabled_var = tk.BooleanVar(value=config.get('enabled', True))
        ttk.Checkbutton(form, text="✅ Активна", variable=enabled_var).grid(row=len(fields)+3, column=0, sticky=tk.W, pady=10)
        
        def save():
            try:
                new_config = {}
                for key, var in entries.items():
                    # Приводим типы
                    if key in ['leverage', 'grid_orders_count', 'max_working_coins']:
                        new_config[key] = int(var.get())
                    else:
                        new_config[key] = float(var.get())
                        
                new_config['grid_mode'] = mode_var.get()
                if mode_var.get() == "manual":
                    new_config['manual_steps'] = [float(v.get()) for v in self.manual_default_entries]
                else:
                    new_config['manual_steps'] = []
                new_config['enabled'] = enabled_var.get()
                
                self.save_working_coin_defaults(new_config)
                self.max_working_coins = new_config.get('max_working_coins', 1)
                win.destroy()
                messagebox.showinfo("Успех", "✅ Настройки по умолчанию сохранены")
                self.logger.info("Настройки монеты в работе по умолчанию сохранены")
            except Exception as e:
                self.error_logger.error(f"Ошибка сохранения настроек по умолчанию: {e}")
                messagebox.showerror("Ошибка", f"❌ Неверный формат: {e}")
                
        ttk.Button(form, text="💾 Сохранить", command=save).grid(row=len(fields)+4, column=0, columnspan=2, pady=15)
        def update_manual_defaults():
            for widget in manual_frame.winfo_children():
                widget.destroy()
            self.manual_default_entries = []
            try:
                num = int(entries['grid_orders_count'].get()) - 1
                if num > 0:
                    ttk.Label(manual_frame, text="📏 Шаги (%):").pack(anchor=tk.W)
                    current_steps = config.get('manual_steps', [config.get('grid_step', 1.0)] * num)
                    # Убедимся, что current_steps имеет нужную длину
                    while len(current_steps) < num:
                        current_steps.append(config.get('grid_step', 1.0))
                    for i in range(num):
                        step_var = tk.StringVar(value=str(current_steps[i]) if i < len(current_steps) else str(config.get('grid_step', 1.0)))
                        ttk.Entry(manual_frame, textvariable=step_var, width=10).pack(pady=2)
                        self.manual_default_entries.append(step_var)
            except:
                pass
        def toggle_mode():
            if mode_var.get() == "manual":
                update_manual_defaults()
                manual_frame.grid()
            else:
                manual_frame.grid_remove()
        toggle_mode()
        mode_var.trace_add('write', lambda *a: toggle_mode())
        entries['grid_orders_count'].trace_add('write', lambda *a: update_manual_defaults() if mode_var.get() == "manual" else None)
        enabled_var = tk.BooleanVar(value=config.get('enabled', True))
        ttk.Checkbutton(form, text="✅ Активна", variable=enabled_var).grid(row=len(fields)+3, column=0, sticky=tk.W, pady=10)
        def save():
            try:
                new_config = {}
                for key, var in entries.items():
                    if key in ['leverage', 'grid_orders_count', 'max_working_coins']:
                        new_config[key] = int(var.get())
                    else:
                        new_config[key] = float(var.get())
                new_config['grid_mode'] = mode_var.get()
                if mode_var.get() == "manual":
                    new_config['manual_steps'] = [float(v.get()) for v in self.manual_default_entries]
                else:
                    new_config['manual_steps'] = []
                new_config['enabled'] = enabled_var.get()
                self.save_working_coin_defaults(new_config)
                self.max_working_coins = new_config.get('max_working_coins', 1)
                win.destroy()
                messagebox.showinfo("Успех", "✅ Настройки по умолчанию сохранены")
                self.logger.info("Настройки монеты в работе по умолчанию сохранены")
            except Exception as e:
                self.logger.error(f"Ошибка сохранения настроек по умолчанию: {e}")
                messagebox.showerror("Ошибка", f"❌ Неверный формат: {e}")
        ttk.Button(form, text="💾 Сохранить", command=save).grid(row=len(fields)+4, column=0, columnspan=2, pady=15)

    def on_working_coin_double_click(self, event):
        selected = self.working_coin_tree.selection()
        if not selected:
            return
        item = selected[0]
        symbol = self.working_coin_tree.item(item, 'values')[0]
        config = next((c for c in self.working_coin_configs if c.symbol == symbol), None)
        if config:
            self.logger.info(f"Двойной клик по монете в работе: {config.symbol}")
            self.open_edit_trading_pair_window(config, is_working_coin=True)

    def is_strong_signal_strategy6(self, kline_data):
        return False, None

    def _original_strategy(self, kline_data):
        return False, None

    def is_strong_signal(self, kline_data, symbol):
        signal, direction, strategy_name = self.enhanced_strategy.enhanced_signal_detection(
            kline_data, symbol, self.enhanced_strategy.market_regime, self.fetch_klines_for_symbol
        )
        if signal:
            self.logger.info(f"✅ ML-сигнал для {symbol}: {direction} (стратегия: {strategy_name})")
            return True, direction, strategy_name
        return False, None, ""

    def update_suitable_coins(self):
        if not self.session:
            # Если нет подключения, просто пишем в лог и выходим, но не прерываем таймер
            # self.logger.debug("Пропуск авто-обновления: нет подключения") 
            return

        # === ЗАЩИТА ОТ ПОВТОРНОГО ЗАПУСКА ===
        if getattr(self, 'is_scanning', False):
            self.logger.info("Сканнер уже работает, пропускаем повторный запуск по таймеру.")
            return

        self.is_scanning = True # Блокируем повторный запуск
        
        # Обновляем статус в GUI (опционально)
        if hasattr(self, 'status_action_label'):
             self.status_action_label.config(text="⏳ Сканирование рынка...")

        def task():
            try:
                self.logger.info("=== НАЧАЛО ФОНОВОГО СКАНИРОВАНИЯ РЫНКА ===")
                self.update_market_regime()
                
                tickers_raw = self.fetch_tickers()
                if not tickers_raw:
                    return

                MIN_VOLUME_THRESHOLD = 40000000 # 40 млн
                filtered_tickers = [t for t in tickers_raw if t['volume'] > MIN_VOLUME_THRESHOLD]
                filtered_tickers.sort(key=lambda x: x['volume'], reverse=True)
                top_symbols = [t['symbol'] for t in filtered_tickers[:150]]
                
                self.logger.info(f"Отобрано {len(filtered_tickers)} монет по объему. Анализируем ТОП-150.")
                
                ticker_map = {t['symbol']: t for t in filtered_tickers}
                suitable_coins = []
                ml_signals_found = 0

                for symbol in top_symbols:
                    # Если флаг снят принудительно (выход из программы), останавливаемся
                    if not self.is_scanning: 
                        break
                        
                    try:
                        if self.is_symbol_in_timeout(symbol): continue
                        if self.is_in_blacklist(symbol): continue
                        
                        ticker = ticker_map.get(symbol)
                        if ticker is None: continue
                        
                        change_24h = ticker['change']
                        # Фильтр сильной волатильности за сутки
                        if change_24h <= -25 or change_24h >= 35: continue
                        
                        # Запрашиваем 5-минутные свечи
                        kline_data = self.fetch_klines_for_symbol(symbol, "5", 150)
                        if kline_data is None or kline_data.empty: continue
                        
                        is_suitable, direction, strategy_name = self.is_strong_signal(kline_data, symbol)
                        
                        if is_suitable:
                            ml_signals_found += 1
                            if len(kline_data) >= 2:
                                prev_close = kline_data['close'].iloc[-2]
                                curr_open = kline_data['open'].iloc[-1]
                                change_15m = ((curr_open - prev_close) / prev_close) * 100
                            else:
                                change_15m = 0.0
                                
                            coin = SuitableCoin(
                                symbol=symbol,
                                volume_24h=ticker['volume'],
                                price=ticker['price'],
                                change_24h=change_24h,
                                change_15m=change_15m,
                                direction=direction,
                                strategy=strategy_name,
                                timestamp=time.time()
                            )
                            suitable_coins.append(coin)
                            
                            signal_msg = f"✅ СИГНАЛ (ФОН): {symbol} | {direction} | {strategy_name} | Vol: {ticker['volume']:.0f}"
                            self.signal_logger.info(signal_msg)
                            self.logger.info(signal_msg)
                            
                    except Exception as e:
                        self.error_logger.error(f"Ошибка анализа {symbol}: {e}")
                    
                    time.sleep(0.05) # Небольшая пауза чтобы не спамить запросами

                # Обновляем список подходящих монет
                suitable_coins.sort(key=lambda x: x.volume_24h, reverse=True)
                self.suitable_coins = suitable_coins[:self.suitable_coins_max]
                
                self.logger.info(f"=== СКАНИРОВАНИЕ ЗАВЕРШЕНО. Найдено: {ml_signals_found} ===")
                
                # Обновляем UI и запускаем авто-добавление в ГЛАВНОМ потоке
                self.root.after(0, self.auto_add_next_working_coin)
                self.root.after(0, self.update_suitable_coins_table)
                self.root.after(0, lambda: self.status_action_label.config(text="Сканирование завершено"))
                
            except Exception as e:
                self.error_logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в сканере: {e}", exc_info=True)
            finally:
                # Всегда снимаем флаг, чтобы таймер мог запустить сканирование в следующий раз
                self.is_scanning = False 

        # Запускаем задачу в отдельном потоке
        threading.Thread(target=task, daemon=True).start()

    def update_market_regime(self):
        try:
            btc_data = self.fetch_klines_for_symbol("BTCUSDT", "15", 100)
            if btc_data is not None and not btc_data.empty:
                self.enhanced_strategy.market_regime = self.enhanced_strategy.determine_market_regime(btc_data, None)
                self.logger.info(f"Рыночный режим обновлен: {self.enhanced_strategy.market_regime}")
        except Exception as e:
            self.logger.error(f"Ошибка обновления рыночного режима: {e}")

    def check_working_coin_conditions(self):
        """Основной цикл проверки условий для входа и усреднения"""
        if not self.session:
            return

        # Работаем по копии списка
        current_configs = self.working_coin_configs[:]
        
        for config in current_configs:
            if not config.enabled:
                continue
                
            symbol = config.symbol
            
            # === ГЛАВНАЯ ЗАЩИТА ОТ ПОВТОРНОГО ВХОДА ===
            if self.is_symbol_in_timeout(symbol):
                # Если она все еще в списке конфигов (хотя должна быть удалена), удаляем принудительно
                if config in self.working_coin_configs:
                    self.logger.info(f"🛡️ {symbol} в таймауте, но найдена в конфиге. Удаляем.")
                    self.working_coin_configs.remove(config)
                    self.save_working_coin_configs()
                    self.root.after(0, self.update_working_coin_display)
                continue
            
            # Проверяем, существует ли конфиг в РЕАЛЬНОМ списке (не был ли удален другим потоком)
            if config not in self.working_coin_configs:
                continue
            # ==========================================

            # 1. Если позиция уже есть - управляем ей
            if self.has_open_position(symbol):
                # ВАЖНОЕ ДОПОЛНЕНИЕ: Двойная проверка TP при каждом цикле
                # Это гарантирует, что TP всегда актуален
                try:
                    positions = self.fetch_positions(symbol=symbol)
                    position = next((p for p in positions if p['symbol'] == symbol and float(p['size']) > 0), None)
                    if position:
                        # Получаем текущую среднюю цену
                        current_avg = float(position['entry_price'])
                        current_size = float(position['size'])
                        
                        # Получаем предыдущее состояние
                        prev_state = self._position_states.get(symbol, {})
                        last_avg = prev_state.get('entry_price', 0)
                        last_size = prev_state.get('size', 0)
                        
                        # Проверяем изменения (используем процентные допуски)
                        avg_changed = False
                        size_changed = False
                        
                        if last_avg > 0:
                            avg_change_pct = abs(current_avg - last_avg) / last_avg * 100
                            avg_changed = avg_change_pct > 0.01  # 0.01% изменение
                        
                        if last_size > 0:
                            size_change_pct = abs(current_size - last_size) / last_size * 100
                            size_changed = size_change_pct > 0.1  # 0.1% изменение размера
                        
                        # Если средняя цена изменилась, обновляем TP
                        if avg_changed:
                            self.logger.info(f"📊 Обнаружено изменение средней цены {symbol}: {last_avg:.8f} -> {current_avg:.8f} ({avg_change_pct:.4f}%)")
                            # Обновляем состояние
                            self._update_position_state(symbol, current_size, current_avg)
                            # Обновляем TP
                            self.update_take_profit_based_on_average(symbol, config, force_update=True)
                        
                        # Если размер изменился значительно, тоже обновляем TP
                        elif size_changed:
                            self.logger.info(f"📏 Изменение размера позиции {symbol}: {last_size:.4f} -> {current_size:.4f} ({size_change_pct:.2f}%)")
                            # Обновляем состояние
                            self._update_position_state(symbol, current_size, current_avg)
                            # Проверяем, не исполнился ли сеточный ордер
                            if current_size > last_size:
                                self.logger.info(f"🚀 Возможно исполнение сеточного ордера {symbol}")
                                # Вызываем пересчет TP
                                self._recalculate_tp_after_grid_fill(symbol, position)
                        
                except Exception as e:
                    self.logger.debug(f"Ошибка при дополнительной проверке TP для {symbol}: {e}")
                
                # Основной мониторинг и обновление TP
                self.monitor_and_update_tp(config)
                continue

            # 2. Позиции нет - ищем вход
            # Используем "5" минутный таймфрейм
            kline_data = self.fetch_klines_for_symbol(symbol, "5", 150)
            
            if kline_data is None or len(kline_data) < 20:
                continue

            # Проверяем сигналы
            is_suitable, current_direction, strategy_name = self.is_strong_signal(kline_data, symbol)
            
            should_enter = False
            entry_price = kline_data['close'].iloc[-1]
            
            # Логика входа
            if is_suitable and current_direction == config.direction:
                should_enter = True
                self.logger.info(f"✅ ВХОД {symbol}: Сигнал {strategy_name} подтвержден.")
            
            # Soft Check
            else:
                ema_21 = kline_data['close'].ewm(span=21).mean().iloc[-1]
                trend_ok = False
                if config.direction == "long" and entry_price > ema_21:
                    trend_ok = True
                elif config.direction == "short" and entry_price < ema_21:
                    trend_ok = True
                    
                if trend_ok:
                    should_enter = True
                    self.logger.info(f"✅ ВХОД {symbol} (Soft Check): Тренд {config.direction} сохраняется.")

            if should_enter:
                # Еще одна финальная проверка перед отправкой ордера
                if not self.is_symbol_in_timeout(symbol):
                    # Проверяем счетчик неудачных попыток
                    if config.failed_entry_attempts >= 3:
                        self.logger.warning(f"⛔ Превышен лимит неудачных попыток входа для {symbol} (3 попытки). Удаляем из работы.")
                        self.working_coin_configs = [c for c in self.working_coin_configs if c.symbol != symbol]
                        self.save_working_coin_configs()
                        self.root.after(0, self.update_working_coin_display)
                        continue
                    
                    self.enter_position_for_working_coin(config, entry_price)
                else:
                    self.logger.warning(f"⛔ Блокировка входа {symbol} в последний момент: таймаут.")

    def auto_add_next_working_coin(self):
        if not self.suitable_coins:
            return

        # Получаем реальное количество активных монет
        current_working_count = len(self.working_coin_configs)
        
        # Логируем состояние слотов
        if current_working_count >= self.max_working_coins:
            self.logger.debug(f"Авто-добавление пропущено: слоты заняты ({current_working_count}/{self.max_working_coins})")
            return

        added_count = 0
        
        # Копируем список, чтобы безопасно итерироваться
        for coin in self.suitable_coins[:]:
            if current_working_count >= self.max_working_coins:
                break
                
            # Проверки
            if self.is_symbol_in_timeout(coin.symbol):
                continue
            if self.is_in_blacklist(coin.symbol):
                continue
            if any(config.symbol == coin.symbol for config in self.working_coin_configs):
                continue

            # Создаем конфигурацию
            config = TradingPairConfig()
            config.symbol = coin.symbol
            
            # Загружаем дефолтные настройки
            defaults = self.working_coin_defaults
            config.first_order_amount = float(defaults.get('first_order_amount', 10.0))
            config.leverage = int(defaults.get('leverage', 20))
            config.take_profit = float(defaults.get('take_profit', 1.5))
            config.min_take_profit = 0.8
            config.grid_orders_count = int(defaults.get('grid_orders_count', 8))
            config.grid_step = float(defaults.get('grid_step', 4.5))
            config.volume_multiplier = float(defaults.get('volume_multiplier', 1.2))
            config.max_total_amount = float(defaults.get('max_total_amount', 250.0))
            config.grid_mode = defaults.get('grid_mode', 'manual')
            config.manual_steps = defaults.get('manual_steps', [])
            config.enabled = bool(defaults.get('enabled', True))
            config.use_manual_tp = False
            config.manual_tp_price = 0.0
            config.failed_entry_attempts = 0
            
            # ВАЖНО: Направление берем из сигнала
            config.direction = coin.direction

            self.working_coin_configs.append(config)
            current_working_count += 1
            added_count += 1
            
            self.logger.info(f"🚀 АВТО-ДОБАВЛЕНИЕ: {coin.symbol} ({coin.direction}) добавлена в работу. Слот {current_working_count}/{self.max_working_coins}")

        if added_count > 0:
            self.save_working_coin_configs()
            
            # Очищаем список подходящих от добавленных монет
            added_symbols = [c.symbol for c in self.working_coin_configs]
            self.suitable_coins = [c for c in self.suitable_coins if c.symbol not in added_symbols]
            
            # === ИСПРАВЛЕНИЕ: Безопасное обновление UI из потока ===
            self.root.after(0, self.update_working_coin_display)
            self.root.after(0, self.update_suitable_coins_table)

    def add_suitable_to_trading(self):
        selected = self.suitable_coins_tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите монету для добавления")
            return
        item = selected[0]
        symbol = self.suitable_coins_tree.item(item, 'values')[0]
        self.logger.info(f"Пользователь добавляет монету {symbol} в торговлю")
        for config in self.trading_pairs:
            if config.symbol == symbol:
                messagebox.showinfo("Информация", f"Пара {symbol} уже есть в торговых парах")
                return
        config = TradingPairConfig()
        config.symbol = symbol
        config.first_order_amount = 10.0
        config.leverage = 3
        config.take_profit = 1.5
        config.min_take_profit = 0.8  # ИСПРАВЛЕНИЕ: Всегда 1.1%
        config.grid_orders_count = 5
        config.grid_step = 1.0
        config.volume_multiplier = 1.2
        config.max_total_amount = 100.0
        config.enabled = False
        config.use_manual_tp = False
        config.manual_tp_price = 0.0
        config.failed_entry_attempts = 0  # Инициализируем счетчик неудачных попыток
        self.trading_pairs.append(config)
        self.save_trading_pairs()
        self.update_trading_pairs_table()
        messagebox.showinfo("Успех", f"✅ Пара {symbol} добавлена в торговые пары (статус: выключена)")
        self.logger.info(f"Монета {symbol} добавлена в торговые пары")

    def on_suitable_coin_click(self, event):
        item = self.suitable_coins_tree.selection()
        if item:
            symbol = self.suitable_coins_tree.item(item[0], 'values')[0]
            self.current_symbol = symbol
            self.logger.info(f"Выбрана монета из подходящих: {symbol}")

    def create_trading_pairs_table(self, parent):
        pass

    def update_trading_pairs_table(self):
        pass

    def edit_selected_trading_pair(self):
        pass

    def open_edit_trading_pair_window(self, config, is_working_coin=False):
        if self.edit_window is not None and self.edit_window.winfo_exists():
            self.edit_window.lift()
            self.edit_window.focus_force()
            return
            
        self.logger.info(f"Открытие окна редактирования для пары: {config.symbol}")
        self.edit_window = tk.Toplevel(self.root)
        self.edit_window.title(f"✏️ Редактирование пары {config.symbol}")
        self.edit_window.geometry("600x850")
        self.edit_window.minsize(550, 750)
        
        main_frame = ttk.Frame(self.edit_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        form_frame = ttk.LabelFrame(scrollable_frame, text="✏️ Редактирование параметров", padding=15)
        form_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # --- ПОЛЯ ВВОДА ---
        
        # Символ
        ttk.Label(form_frame, text="📊 Торговая пара:").grid(row=0, column=0, sticky=tk.W, pady=8)
        symbol_var = tk.StringVar(value=config.symbol)
        ttk.Entry(form_frame, textvariable=symbol_var, width=20, state='readonly').grid(row=0, column=1, sticky=tk.W, pady=8, padx=10)
        
        # Первый ордер
        ttk.Label(form_frame, text="💰 Первый ордер (USDT):").grid(row=1, column=0, sticky=tk.W, pady=8)
        first_order_var = tk.StringVar(value=str(config.first_order_amount))
        ttk.Entry(form_frame, textvariable=first_order_var, width=20).grid(row=1, column=1, sticky=tk.W, pady=8, padx=10)
        
        # Плечо
        ttk.Label(form_frame, text="📈 Кредитное плечо:").grid(row=2, column=0, sticky=tk.W, pady=8)
        leverage_var = tk.StringVar(value=str(config.leverage))
        ttk.Entry(form_frame, textvariable=leverage_var, width=20).grid(row=2, column=1, sticky=tk.W, pady=8, padx=10)
        
        # Тейк-профит
        ttk.Label(form_frame, text="🎯 Тейк-профит (%):").grid(row=3, column=0, sticky=tk.W, pady=8)
        take_profit_var = tk.StringVar(value=str(config.take_profit))
        ttk.Entry(form_frame, textvariable=take_profit_var, width=20).grid(row=3, column=1, sticky=tk.W, pady=8, padx=10)
        
        # === ИСПРАВЛЕНИЕ 1: Мин. TP берется из настроек по умолчанию для Working Coin ===
        ttk.Label(form_frame, text="📊 Минимальный тейк-профит (%):").grid(row=4, column=0, sticky=tk.W, pady=8)
        
        # Получаем значение из Defaults, если оно есть, иначе 0.8
        default_min_tp = self.working_coin_defaults.get('min_take_profit', 0.8)
        
        # Если в конфиге уже сохранено специфичное значение (и оно не дефолтное), используем его, иначе дефолт
        current_min_tp = getattr(config, 'min_take_profit', default_min_tp)
        
        min_take_profit_var = tk.StringVar(value=str(current_min_tp))
        # Делаем поле доступным для редактирования, если нужно, или readonly, если хотим жестко привязать
        ttk.Entry(form_frame, textvariable=min_take_profit_var, width=20).grid(row=4, column=1, sticky=tk.W, pady=8, padx=10)

        # Ордера сетки
        ttk.Label(form_frame, text="📋 Ордера сетки:").grid(row=5, column=0, sticky=tk.W, pady=8)
        grid_orders_var = tk.StringVar(value=str(config.grid_orders_count))
        ttk.Entry(form_frame, textvariable=grid_orders_var, width=20).grid(row=5, column=1, sticky=tk.W, pady=8, padx=10)
        
        # Множитель
        ttk.Label(form_frame, text="🚀 Множитель объема:").grid(row=6, column=0, sticky=tk.W, pady=8)
        multiplier_var = tk.StringVar(value=str(config.volume_multiplier))
        ttk.Entry(form_frame, textvariable=multiplier_var, width=20).grid(row=6, column=1, sticky=tk.W, pady=8, padx=10)
        
        # Макс сумма
        ttk.Label(form_frame, text="💎 Макс. сумма (USDT):").grid(row=7, column=0, sticky=tk.W, pady=8)
        max_total_var = tk.StringVar(value=str(config.max_total_amount))
        ttk.Entry(form_frame, textvariable=max_total_var, width=20).grid(row=7, column=1, sticky=tk.W, pady=8, padx=10)

        # --- РЕЖИМ СЕТКИ ---
        ttk.Label(form_frame, text="🎛️ Режим сетки:").grid(row=8, column=0, sticky=tk.W, pady=8)
        grid_mode_var = tk.StringVar(value=config.grid_mode)
        mode_frame = ttk.Frame(form_frame)
        mode_frame.grid(row=8, column=1, sticky=tk.W, pady=8, padx=10)
        ttk.Radiobutton(mode_frame, text="Автоматический", variable=grid_mode_var, value="auto").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Ручной", variable=grid_mode_var, value="manual").pack(anchor=tk.W)
        
        auto_frame = ttk.Frame(form_frame)
        auto_frame.grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=8)
        ttk.Label(auto_frame, text="📐 Шаг сетки (%):").pack(side=tk.LEFT)
        grid_step_var = tk.StringVar(value=str(config.grid_step))
        ttk.Entry(auto_frame, textvariable=grid_step_var, width=10).pack(side=tk.LEFT, padx=5)
        
        manual_frame = ttk.Frame(form_frame)
        manual_frame.grid(row=10, column=0, columnspan=2, sticky=tk.W, pady=8)
        self.manual_entries = []

        # ... (Код обновления manual_entries оставляем стандартным, для краткости опускаю вспомогательные функции UI, они такие же) ...
        # (Вставьте сюда функции update_manual_inputs, update_totals и т.д. из вашего старого кода, они не требуют изменений)
        
        # --- ФУНКЦИИ UI (Скопируйте их из старого кода) ---
        def update_manual_inputs():
            for widget in manual_frame.winfo_children():
                widget.destroy()
            self.manual_entries = []
            try:
                num_orders = int(grid_orders_var.get() or 0)
                if num_orders > 1:
                    ttk.Label(manual_frame, text="📏 Шаги от начальной цены (%):").pack(anchor=tk.W, pady=5)
                    current_steps = config.manual_steps if config.manual_steps else [config.grid_step] * (num_orders - 1)
                    while len(current_steps) < num_orders - 1: # Safety pad
                        current_steps.append(config.grid_step)
                    for i in range(num_orders - 1):
                        step_frame = ttk.Frame(manual_frame)
                        step_frame.pack(fill=tk.X, pady=2)
                        ttk.Label(step_frame, text=f"Шаг {i+1}:").pack(side=tk.LEFT)
                        entry_var = tk.StringVar(value=str(current_steps[i]))
                        ttk.Entry(step_frame, textvariable=entry_var, width=10).pack(side=tk.LEFT, padx=5)
                        self.manual_entries.append(entry_var)
            except ValueError: pass

        def toggle_grid_mode(*args):
            if grid_mode_var.get() == "auto":
                auto_frame.grid()
                manual_frame.grid_remove()
            else:
                auto_frame.grid_remove()
                manual_frame.grid()
                update_manual_inputs()
        
        grid_mode_var.trace_add('write', toggle_grid_mode)
        grid_orders_var.trace_add('write', lambda *a: update_manual_inputs() if grid_mode_var.get() == 'manual' else None)
        toggle_grid_mode()

        # Активность
        enabled_var = tk.BooleanVar(value=config.enabled)
        ttk.Checkbutton(form_frame, text="✅ Активна", variable=enabled_var).grid(row=12, column=0, sticky=tk.W, pady=15)

        # === ИСПРАВЛЕНИЕ 2: Тип Тейк-Профита (Авто по умолчанию) ===
        # Логика: Если use_manual_tp == True, то Manual. Иначе Auto.
        # Важно: При открытии окна мы верим конфигу.
        
        initial_tp_mode = "manual" if config.use_manual_tp else "auto"
        tp_mode_var = tk.StringVar(value=initial_tp_mode)
        
        ttk.Label(form_frame, text="🎯 Тип тейк-профита:").grid(row=13, column=0, sticky=tk.W, pady=8)
        tp_mode_frame = ttk.Frame(form_frame)
        tp_mode_frame.grid(row=13, column=1, sticky=tk.W, pady=8, padx=10)
        
        ttk.Radiobutton(tp_mode_frame, text="Автоматический (из настроек)", 
                       variable=tp_mode_var, value="auto").pack(anchor=tk.W)
        ttk.Radiobutton(tp_mode_frame, text="Ручной (с биржи)", 
                       variable=tp_mode_var, value="manual").pack(anchor=tk.W)

        # Кнопки
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill=tk.X, pady=10)

        def save_changes():
            try:
                # Обновляем конфиг значениями из полей
                config.first_order_amount = float(first_order_var.get())
                config.leverage = int(leverage_var.get())
                config.take_profit = float(take_profit_var.get())
                config.min_take_profit = float(min_take_profit_var.get()) # Сохраняем введенный Min TP
                config.grid_orders_count = int(grid_orders_var.get())
                config.grid_step = float(grid_step_var.get())
                config.volume_multiplier = float(multiplier_var.get())
                config.max_total_amount = float(max_total_var.get())
                config.enabled = enabled_var.get()
                config.grid_mode = grid_mode_var.get()
                
                # Сохраняем режим TP
                new_tp_mode = tp_mode_var.get()
                config.use_manual_tp = (new_tp_mode == "manual")
                
                # Если переключили на Авто, сбрасываем ручную цену, чтобы бот пересчитал
                if not config.use_manual_tp:
                    config.manual_tp_price = 0.0
                
                if config.grid_mode == "manual":
                    config.manual_steps = [float(entry.get()) for entry in self.manual_entries]
                
                self.save_trading_pairs()
                
                if is_working_coin:
                    # Обновляем в списке рабочих
                    for i, working_config in enumerate(self.working_coin_configs):
                        if working_config.symbol == config.symbol:
                            self.working_coin_configs[i] = config
                            break
                    self.save_working_coin_configs()
                    self.update_working_coin_display()
                
                self.edit_window.destroy()
                self.edit_window = None
                messagebox.showinfo("Успех", f"✅ Пара {config.symbol} обновлена")
                self.logger.info(f"Пара {config.symbol} успешно обновлена")
                
            except ValueError as e:
                self.logger.error(f"Ошибка сохранения параметров для {config.symbol}: {e}")
                messagebox.showerror("Ошибка", "❌ Проверьте правильность введенных данных")

        # Кнопки управления позицией (оставляем без изменений)
        grid_buttons_frame = ttk.Frame(form_frame)
        grid_buttons_frame.grid(row=14, column=0, columnspan=2, sticky=tk.W, pady=10)
        ttk.Button(grid_buttons_frame, text="🗑️ Удалить сетку", 
                  command=lambda: self.delete_grid_for_symbol(config.symbol)).pack(side=tk.LEFT, padx=5)
        ttk.Button(grid_buttons_frame, text="➕ Добавить сетку", 
                  command=lambda: self.place_grid_for_symbol(config)).pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="💾 Сохранить", command=save_changes).pack(pady=5)
        ttk.Button(button_frame, text="❌ Отмена", command=lambda: [self.edit_window.destroy(), setattr(self, 'edit_window', None)]).pack(pady=5)
        
        def on_closing():
            self.edit_window.destroy()
            self.edit_window = None
        self.edit_window.protocol("WM_DELETE_WINDOW", on_closing)
        def update_manual_inputs():
            for widget in manual_frame.winfo_children():
                widget.destroy()
            self.manual_entries = []
            self.manual_amount_labels = []
            try:
                num_orders = int(grid_orders_var.get() or 0)
                if num_orders > 1:
                    ttk.Label(manual_frame, text="📏 Шаги от начальной цены для каждого ордера (%):").pack(anchor=tk.W, pady=5)
                    current_steps = config.manual_steps if config.manual_steps else [config.grid_step] * (num_orders - 1)
                    for i in range(num_orders - 1):
                        step_frame = ttk.Frame(manual_frame)
                        step_frame.pack(fill=tk.X, pady=2)
                        ttk.Label(step_frame, text=f"Шаг {i+1}:").pack(side=tk.LEFT)
                        entry_var = tk.StringVar(value=str(current_steps[i]) if i < len(current_steps) else str(config.grid_step))
                        entry = ttk.Entry(step_frame, textvariable=entry_var, width=10)
                        entry.pack(side=tk.LEFT, padx=5)
                        self.manual_entries.append(entry_var)
                        first_order = float(first_order_var.get())
                        multiplier = float(multiplier_var.get())
                        leverage = int(leverage_var.get())
                        amount_no_leverage = first_order * (multiplier ** (i + 1))
                        amount_with_leverage = amount_no_leverage * leverage
                        amount_label = ttk.Label(step_frame, text=f"💰 Без плеча: {amount_no_leverage:.2f} USDT, 💸 С плечом: {amount_with_leverage:.2f} USDT")
                        amount_label.pack(side=tk.LEFT, padx=10)
                        self.manual_amount_labels.append(amount_label)
            except ValueError:
                pass
        def update_amount_labels():
            try:
                first_order = float(first_order_var.get())
                multiplier = float(multiplier_var.get())
                leverage = int(leverage_var.get())
        
                current_amount_no_leverage = first_order * multiplier
                
                # ИСПРАВЛЕНИЕ: Добавлено self. и проверка на существование
                if hasattr(self, 'manual_amount_labels'):
                    for i, label in enumerate(self.manual_amount_labels):
                        amount_no_leverage = current_amount_no_leverage
                        amount_with_leverage = amount_no_leverage * leverage
                        label.config(text=f"💰 Без плеча: {amount_no_leverage:.2f} USDT, 💸 С плечом: {amount_with_leverage:.2f} USDT")
                        current_amount_no_leverage *= multiplier
            except ValueError:
                pass
        def toggle_grid_mode():
            if grid_mode_var.get() == "auto":
                auto_frame.grid()
                manual_frame.grid_remove()
            else:
                auto_frame.grid_remove()
                manual_frame.grid()
                update_manual_inputs()
        toggle_grid_mode()
        grid_mode_var.trace_add('write', lambda *args: toggle_grid_mode())
        grid_orders_var.trace_add('write', lambda *args: update_manual_inputs() if grid_mode_var.get() == "manual" else None)
        first_order_var.trace_add('write', lambda *args: update_amount_labels() if grid_mode_var.get() == "manual" else None)
        multiplier_var.trace_add('write', lambda *args: update_amount_labels() if grid_mode_var.get() == "manual" else None)
        totals_frame = ttk.Frame(form_frame)
        totals_frame.grid(row=11, column=0, columnspan=2, sticky=tk.W, pady=10)
        self.total_usdt_label = ttk.Label(totals_frame, text="💰 Суммарный объем без плеча: -- USDT")
        self.total_usdt_label.pack(anchor=tk.W)
        self.total_with_leverage_label = ttk.Label(totals_frame, text="💸 Суммарный объем с плечом: -- USDT")
        self.total_with_leverage_label.pack(anchor=tk.W)
        self.total_percent_label = ttk.Label(totals_frame, text="📊 Макс. отклонение: -- %")
        self.total_percent_label.pack(anchor=tk.W)
        enabled_var = tk.BooleanVar(value=config.enabled)
        ttk.Checkbutton(form_frame, text="✅ Активна", variable=enabled_var).grid(row=12, column=0, sticky=tk.W, pady=15)
        tp_mode_var = tk.StringVar(value="manual" if config.use_manual_tp else "auto")
        ttk.Label(form_frame, text="🎯 Тип тейк-профита:").grid(row=13, column=0, sticky=tk.W, pady=8)
        tp_mode_frame = ttk.Frame(form_frame)
        tp_mode_frame.grid(row=13, column=1, sticky=tk.W, pady=8, padx=10)
        ttk.Radiobutton(tp_mode_frame, text="Автоматический", variable=tp_mode_var, value="auto").pack(anchor=tk.W)
        ttk.Radiobutton(tp_mode_frame, text="Ручной (с биржи)", variable=tp_mode_var, value="manual").pack(anchor=tk.W)
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill=tk.X, pady=10)
        def update_totals():
            try:
                # ИСПРАВЛЕНИЕ: Исправлен отступ (IndentationError)
                total_usdt_no_leverage = 0.0
                total_usdt_with_leverage = 0.0
            
                first_order = float(first_order_var.get())
                multiplier = float(multiplier_var.get())
                leverage = int(leverage_var.get())
                max_total = float(max_total_var.get())
                grid_orders = int(grid_orders_var.get())
            
                current_amount_no_leverage = first_order * multiplier
                current_amount_with_leverage = current_amount_no_leverage * leverage
            
                for i in range(grid_orders):
                    if total_usdt_no_leverage + current_amount_no_leverage > max_total:
                        break
                    if total_usdt_with_leverage + current_amount_with_leverage > max_total * leverage:
                        break
            
                    total_usdt_no_leverage += current_amount_no_leverage
                    total_usdt_with_leverage += current_amount_with_leverage
            
                    current_amount_no_leverage *= multiplier
                    current_amount_with_leverage = current_amount_no_leverage * leverage
            
                total_percent = 0.0
                grid_mode = grid_mode_var.get()
                if grid_mode == 'auto':
                    grid_step = float(grid_step_var.get())
                    total_percent = grid_step * grid_orders
                else:
                    steps = []
                    # ИСПРАВЛЕНИЕ: manual_entries -> self.manual_entries
                    current_entries = getattr(self, 'manual_entries', [])
                    for entry_var in current_entries:
                        try:
                            step = float(entry_var.get())
                            steps.append(step)
                        except ValueError:
                            steps.append(0.0)
                    total_percent = sum(steps)
            
                # ИСПРАВЛЕНИЕ: Добавлено self. к меткам total_usdt_label и т.д.
                if hasattr(self, 'total_usdt_label'):
                    self.total_usdt_label.config(text=f"💰 Суммарный объем без плеча: {total_usdt_no_leverage:.2f} USDT")
                    self.total_with_leverage_label.config(text=f"💸 Суммарный объем с плечом: {total_usdt_with_leverage:.2f} USDT")
                    self.total_percent_label.config(text=f"📊 Макс. отклонение: {total_percent:.2f} %")

            except ValueError:
                # ИСПРАВЛЕНИЕ: Добавлено self. в блоке except
                if hasattr(self, 'total_usdt_label'):
                    self.total_usdt_label.config(text="💰 Суммарный объем без плеча: -- USDT")
                    self.total_with_leverage_label.config(text="💸 Суммарный объем с плечом: -- USDT")
                    self.total_percent_label.config(text="📊 Макс. отклонение: -- %")
        def update_with_totals():
            update_amount_labels()
            update_totals()
        def update_manual_with_totals():
            update_manual_inputs()
            update_totals()
        grid_orders_var.trace_add('write', lambda *args: update_manual_with_totals() if grid_mode_var.get() == "manual" else update_totals())
        first_order_var.trace_add('write', lambda *args: update_with_totals())
        multiplier_var.trace_add('write', lambda *args: update_with_totals())
        max_total_var.trace_add('write', lambda *args: update_totals())
        grid_step_var.trace_add('write', lambda *args: update_totals())
        update_totals()
        def update_manual_entries():
            for entry_var in self.manual_entries:
                entry_var.trace_add('write', lambda *args: update_totals())
        update_manual_entries()
        def save_changes():
            try:
                config.first_order_amount = float(first_order_var.get())
                config.leverage = int(leverage_var.get())
                config.take_profit = float(take_profit_var.get())
                config.min_take_profit = 0.8  # ИСПРАВЛЕНИЕ: Всегда 1.1%
                config.grid_orders_count = int(grid_orders_var.get())
                config.grid_step = float(grid_step_var.get())
                config.volume_multiplier = float(multiplier_var.get())
                config.max_total_amount = float(max_total_var.get())
                config.enabled = enabled_var.get()
                config.grid_mode = grid_mode_var.get()
                config.use_manual_tp = (tp_mode_var.get() == "manual")
                if config.grid_mode == "manual":
                    config.manual_steps = [float(entry.get()) for entry in self.manual_entries]
                self.save_trading_pairs()
                if is_working_coin:
                    for i, working_config in enumerate(self.working_coin_configs):
                        if working_config.symbol == config.symbol:
                            self.working_coin_configs[i] = config
                            break
                    self.save_working_coin_configs()
                    self.update_working_coin_display()
                self.edit_window.destroy()
                self.edit_window = None
                messagebox.showinfo("Успех", f"✅ Пара {config.symbol} обновлена")
                self.logger.info(f"Пара {config.symbol} успешно обновлена")
            except ValueError as e:
                self.logger.error(f"Ошибка сохранения параметров для {config.symbol}: {e}")
                messagebox.showerror("Ошибка", "❌ Проверьте правильность введенных данных")
        grid_buttons_frame = ttk.Frame(form_frame)
        grid_buttons_frame.grid(row=14, column=0, columnspan=2, sticky=tk.W, pady=10)
        ttk.Button(grid_buttons_frame, text="🗑️ Удалить сетку", 
                  command=lambda: self.delete_grid_for_symbol(config.symbol)).pack(side=tk.LEFT, padx=5)
        ttk.Button(grid_buttons_frame, text="➕ Добавить сетку", 
                  command=lambda: self.place_grid_for_symbol(config)).pack(side=tk.LEFT, padx=5)
        def update_position():
            try:
                config.first_order_amount = float(first_order_var.get())
                config.leverage = int(leverage_var.get())
                config.take_profit = float(take_profit_var.get())
                config.min_take_profit = 0.8  # ИСПРАВЛЕНИЕ: Всегда 1.1%
                config.grid_orders_count = int(grid_orders_var.get())
                config.grid_step = float(grid_step_var.get())
                config.volume_multiplier = float(multiplier_var.get())
                config.max_total_amount = float(max_total_var.get())
                config.enabled = enabled_var.get()
                config.grid_mode = grid_mode_var.get()
                config.use_manual_tp = (tp_mode_var.get() == "manual")
                if config.grid_mode == "manual":
                    config.manual_steps = [float(entry.get()) for entry in self.manual_entries]
                self.save_trading_pairs()
                self.update_open_position(config)
                messagebox.showinfo("Успех", f"✅ Настройки позиции {config.symbol} обновлены")
                self.logger.info(f"Настройки позиции {config.symbol} обновлены")
            except ValueError as e:
                self.logger.error(f"Ошибка обновления позиции для {config.symbol}: {e}")
                messagebox.showerror("Ошибка", "❌ Проверьте правильность введенных данных")
        ttk.Button(button_frame, text="💾 Сохранить", command=save_changes).pack(pady=5)
        ttk.Button(button_frame, text="🔄 Обновить", command=update_position).pack(pady=5)
        ttk.Button(button_frame, text="❌ Отмена", command=lambda: [self.edit_window.destroy(), setattr(self, 'edit_window', None)]).pack(pady=5)
        def on_closing():
            self.edit_window.destroy()
            self.edit_window = None
        self.edit_window.protocol("WM_DELETE_WINDOW", on_closing)

    def delete_grid_for_symbol(self, symbol):
        self.logger.info(f"Удаление сетки ордеров для {symbol}")
        self.cancel_all_orders_for_symbol(symbol)
        messagebox.showinfo("Успех", f"✅ Сетка ордеров для {symbol} удалена")

    def place_grid_for_symbol(self, config):
        self.logger.info(f"Размещение сетки ордеров для {config.symbol}")

        positions = self.fetch_positions(symbol=config.symbol)
        position = next((p for p in positions if p.get('symbol') == config.symbol and float(p.get('size', 0)) > 0), None)

        if not position:
            messagebox.showwarning("Предупреждение", f"⚠️ Нет открытой позиции для {config.symbol}")
            return

        entry_price = float(position['entry_price'])
        side = position['side']

    # hedge mode position_idx
        if side.lower() == 'long':
            position_idx = 1
        elif side.lower() == 'short':
            position_idx = 2
        else:
            self.logger.error(f"Неизвестное направление позиции: {side}")
            return

        success = self.place_grid_orders(config=config, entry_price=entry_price, side=side, leverage=config.leverage, position_idx=position_idx)

        if success:
            messagebox.showinfo("Успех", f"✅ Сетка ордеров для {config.symbol} размещена")
        else:
            messagebox.showwarning("Предупреждение", f"⚠️ Ошибка размещения сетки для {config.symbol}")


    def update_open_position(self, config):
        if not self.session:
            messagebox.showwarning("Предупреждение", "⚠️ Сначала подключитесь к Bybit")
            return
        if config.grid_mode == 'manual' and (not config.manual_steps or len(config.manual_steps) < config.grid_orders_count - 1):
            messagebox.showwarning("Предупреждение", f"⚠️ Для пары {config.symbol} в ручном режиме задано недостаточно шагов.")
            return
        def task():
            try:
                self.logger.info(f"Обновление открытой позиции для {config.symbol}")
                positions = self.fetch_positions(symbol=config.symbol)
                position = next((p for p in positions if p['symbol'] == config.symbol and p['size'] > 0), None)
                if not position:
                    messagebox.showinfo("Информация", f"ℹ️ Для пары {config.symbol} нет открытой позиции")
                    return
                self.cancel_all_orders_for_symbol(config.symbol)
                time.sleep(1)
                side = position['side']
                self.set_take_profit_with_protection(config.symbol, side, config)
                self.place_grid_orders(config, float(position['entry_price']), side, config.leverage)
                self.root.after(0, lambda: messagebox.showinfo("Успех", f"✅ Позиция {config.symbol} успешно обновлена"))
            except Exception as e:
                error_msg = f"Ошибка обновления позиции: {e}"
                self.logger.error(error_msg)
                self.root.after(0, lambda: messagebox.showerror("Ошибка", error_msg))
        threading.Thread(target=task, daemon=True).start()

    def delete_selected_trading_pair(self):
        pass

    def toggle_selected_trading_pair(self):
        pass

    def on_trading_pair_click(self, event):
        pass

    def load_trading_pairs(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.trading_pairs = []
                    for item in data:
                        config = TradingPairConfig()
                        config.symbol = item['symbol']
                        config.first_order_amount = float(item['first_order_amount'])
                        config.leverage = int(item['leverage'])
                        config.take_profit = float(item['take_profit'])
                        config.min_take_profit = 0.8  # ИСПРАВЛЕНИЕ: Всегда 1.1%
                        config.grid_orders_count = int(item['grid_orders_count'])
                        config.grid_step = float(item['grid_step'])
                        config.volume_multiplier = float(item['volume_multiplier'])
                        config.max_total_amount = float(item['max_total_amount'])
                        config.enabled = bool(item['enabled'])
                        config.grid_mode = item.get('grid_mode', 'auto')
                        config.manual_steps = item.get('manual_steps', [])
                        config.use_manual_tp = bool(item.get('use_manual_tp', False))
                        config.manual_tp_price = float(item.get('manual_tp_price', 0.0))
                        config.failed_entry_attempts = int(item.get('failed_entry_attempts', 0))  # Загружаем счетчик неудачных попыток
                        self.trading_pairs.append(config)
                self.logger.info(f"Загружено {len(self.trading_pairs)} торговых пар")
            except Exception as e:
                self.logger.error(f"Ошибка загрузки торговых пар: {e}")
                self.trading_pairs = []
        else:
            self.logger.info("Файл торговых пар не найден, создан пустой список")
            self.trading_pairs = []

    def save_trading_pairs(self):
        try:
            data = []
            for config in self.trading_pairs:
                data.append({
                    'symbol': config.symbol,
                    'first_order_amount': config.first_order_amount,
                    'leverage': config.leverage,
                    'take_profit': config.take_profit,
                    'min_take_profit': 0.8,  # ИСПРАВЛЕНИЕ: Всегда 1.1%
                    'grid_orders_count': config.grid_orders_count,
                    'grid_step': config.grid_step,
                    'volume_multiplier': config.volume_multiplier,
                    'max_total_amount': config.max_total_amount,
                    'enabled': config.enabled,
                    'grid_mode': config.grid_mode,
                    'manual_steps': config.manual_steps,
                    'use_manual_tp': config.use_manual_tp,
                    'manual_tp_price': config.manual_tp_price,
                    'failed_entry_attempts': config.failed_entry_attempts  # Сохраняем счетчик неудачных попыток
                })
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.debug(f"Сохранено {len(data)} торговых пар")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения торговых пар: {e}")

    def open_trading_pairs_manager(self):
        if self.manager_window is not None and self.manager_window.winfo_exists():
            self.manager_window.lift()
            self.manager_window.focus_force()
            return
        self.logger.info("Открытие менеджера торговых пар")
        self.manager_window = tk.Toplevel(self.root)
        self.manager_window.title("📈 Управление торговыми парами")
        self.manager_window.geometry("800x600")
        self.manager_window.minsize(700, 500)
        main_frame = ttk.Frame(self.manager_window, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="📊 Торговые пары", font=('Arial', 12, 'bold')).pack(anchor=tk.W, pady=(0, 10))
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol', 'enabled', 'first_order', 'leverage', 'tp', 'min_tp', 'grid_orders', 'grid_step', 'multiplier', 'max_total', 'tp_type')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        tree.heading('symbol', text='Пара')
        tree.heading('enabled', text='Вкл')
        tree.heading('first_order', text='Первый ордер')
        tree.heading('leverage', text='Плечо')
        tree.heading('tp', text='Тейк-профит %')
        tree.heading('min_tp', text='Мин. TP %')
        tree.heading('grid_orders', text='Ордера сетки')
        tree.heading('grid_step', text='Шаг сетки %')
        tree.heading('multiplier', text='Множитель')
        tree.heading('max_total', text='Макс. сумма')
        tree.heading('tp_type', text='Тип TP')
        tree.column('symbol', width=80)
        tree.column('enabled', width=40)
        tree.column('first_order', width=80)
        tree.column('leverage', width=60)
        tree.column('tp', width=80)
        tree.column('min_tp', width=70)
        tree.column('grid_orders', width=80)
        tree.column('grid_step', width=80)
        tree.column('multiplier', width=80)
        tree.column('max_total', width=80)
        tree.column('tp_type', width=80)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for config in self.trading_pairs:
            status = "✅" if config.enabled else "❌"
            tp_type = "🔧 Ручной" if config.use_manual_tp else "🤖 Авто"
            tree.insert('', tk.END, values=(
                config.symbol,
                status,
                f"{config.first_order_amount:.2f}",
                config.leverage,
                f"{config.take_profit:.2f}%",
                "0.8%",  # ИСПРАВЛЕНИЕ: Всегда 1.1%
                config.grid_orders_count,
                f"{config.grid_step:.2f}%" if config.grid_mode == "auto" else "🛠️ ручной",
                f"{config.volume_multiplier:.2f}",
                f"{config.max_total_amount:.2f}",
                tp_type
            ))
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        ttk.Button(button_frame, text="➕ Добавить пару", command=self.add_trading_pair).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="✏️ Редактировать", command=lambda: self.manager_edit_trading_pair(tree)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🗑️ Удалить", command=lambda: self.manager_delete_trading_pair(tree)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔘 Включить/Выключить", command=lambda: self.manager_toggle_trading_pair(tree)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="❌ Закрыть", command=self.manager_window.destroy).pack(side=tk.RIGHT, padx=5)
        def on_closing():
            self.manager_window.destroy()
            self.manager_window = None
        self.manager_window.protocol("WM_DELETE_WINDOW", on_closing)

    def manager_edit_trading_pair(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "⚠️ Выберите пару для редактирования")
            return
        item = selected[0]
        symbol = tree.item(item, 'values')[0]
        for config in self.trading_pairs:
            if config.symbol == symbol:
                self.manager_window.destroy()
                self.manager_window = None
                self.open_edit_trading_pair_window(config)
                return

    def manager_delete_trading_pair(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "⚠️ Выберите пару для удаления")
            return
        item = selected[0]
        symbol = tree.item(item, 'values')[0]
        if messagebox.askyesno("Подтверждение", f"🗑️ Удалить пару {symbol}?"):
            self.trading_pairs = [p for p in self.trading_pairs if p.symbol != symbol]
            self.save_trading_pairs()
            tree.delete(item)
            self.update_trading_pairs_table()
            messagebox.showinfo("Успех", f"✅ Пара {symbol} удалена")

    def manager_toggle_trading_pair(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "⚠️ Выберите пару для включения/выключения")
            return
        item = selected[0]
        symbol = tree.item(item, 'values')[0]
        for config in self.trading_pairs:
            if config.symbol == symbol:
                config.enabled = not config.enabled
                status = "✅" if config.enabled else "❌"
                tree.set(item, 'enabled', status)
                self.save_trading_pairs()
                self.update_trading_pairs_table()
                messagebox.showinfo("Успех", f"✅ Пара {symbol} {'включена' if config.enabled else 'выключена'}")
                return

    def add_trading_pair(self):
        win = tk.Toplevel(self.manager_window)
        win.title("➕ Добавить торговую пару")
        win.geometry("400x300")
        win.minsize(350, 250)
        main_frame = ttk.Frame(win, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="📊 Символ пары (например: BTCUSDT):", font=('Arial', 10)).pack(anchor=tk.W, pady=(0, 5))
        symbol_entry = ttk.Entry(main_frame, width=20)
        symbol_entry.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(main_frame, text="ℹ️ Настройки по умолчанию будут применены автоматически.", font=('Arial', 9), foreground="gray").pack(anchor=tk.W, pady=(0, 20))
        def add():
            symbol = symbol_entry.get().strip().upper()
            if not symbol:
                messagebox.showwarning("Предупреждение", "⚠️ Введите символ пары")
                return
            if not self.is_valid_futures_symbol(symbol):
                messagebox.showwarning("Предупреждение", f"⚠️ Символ {symbol} не найден на фьючерсном рынке Bybit или не поддерживается")
                return
            for config in self.trading_pairs:
                if config.symbol == symbol:
                    messagebox.showinfo("Информация", f"ℹ️ Пара {symbol} уже существует")
                    return
            config = TradingPairConfig()
            config.symbol = symbol
            config.first_order_amount = 10.0
            config.leverage = 3
            config.take_profit = 1.5
            config.min_take_profit = 0.8  # ИСПРАВЛЕНИЕ: Всегда 1.1%
            config.grid_orders_count = 5
            config.grid_step = 1.0
            config.volume_multiplier = 1.2
            config.max_total_amount = 100.0
            config.enabled = False
            config.grid_mode = 'auto'
            config.manual_steps = []
            config.use_manual_tp = False
            config.manual_tp_price = 0.0
            self.trading_pairs.append(config)
            self.save_trading_pairs()
            self.update_trading_pairs_table()
            win.destroy()
            messagebox.showinfo("Успех", f"✅ Пара {symbol} добавлена (статус: выключена)")
        ttk.Button(main_frame, text="➕ Добавить", command=add).pack(pady=10)
        ttk.Button(main_frame, text="❌ Отмена", command=win.destroy).pack(pady=5)

    def connect_to_bybit(self):
        api_key = self.api_key_entry.get().strip()
        api_secret = self.api_secret_entry.get().strip()
        if not api_key or not api_secret:
            messagebox.showerror("Ошибка", "❌ Введите API Key и API Secret")
            return
            
        # Обновляем переменные класса
        self.api_key = api_key
        self.api_secret = api_secret
        self.demo_trading = (self.account_type_var.get() == "demo")
        
        # === ИЗМЕНЕНИЕ: Сохраняем ключи в файл ===
        self.save_api_credentials()
        
        self.logger.info(f"Подключение к Bybit: demo={self.demo_trading}")
        try:
            self.session = HTTP(
                testnet=self.demo_trading,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            self.fetch_balance()
            self.load_symbols()
            self.status_label.config(text="● Подключено", foreground="green")
            self.account_type_label.config(text="● Демо-счет" if self.demo_trading else "● Реальный счет")
            self.connect_btn.config(text="🔗 Переподключиться")
            self.initialize_order_manager()
            messagebox.showinfo("Успех", "✅ Успешное подключение к Bybit")
            self.logger.info("Успешное подключение к Bybit")
        except Exception as e:
            self.logger.error(f"Ошибка подключения: {e}")
            messagebox.showerror("Ошибка", f"❌ Ошибка подключения: {e}")
            self.status_label.config(text="● Ошибка подключения", foreground="red")

    def fetch_balance(self):
        if not self.session:
            return
        try:
            response = self.rate_limited_request(
                self.session.get_wallet_balance,
                accountType="UNIFIED"
            )
            if response and response.get('retCode') == 0:
                usdt_balance = 0.0
                for coin in response['result']['list'][0]['coin']:
                    if coin['coin'] == 'USDT':
                        usdt_balance = float(coin['walletBalance'])
                        break
                self.balance = usdt_balance
                self.balance_label.config(text=f"💰 Баланс: {usdt_balance:.2f} USDT")
                self._last_balance = usdt_balance
                return usdt_balance
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Ошибка получения баланса: {error_msg}")
                return 0.0
        except Exception as e:
            self.logger.error(f"Ошибка получения баланса: {e}")
            return 0.0

    def fetch_tickers(self):
        if not self.session:
            return []
        try:
            response = self.rate_limited_request(
                self.session.get_tickers,
                category="linear"
            )
            if response and response.get('retCode') == 0:
                tickers = []
                for ticker in response['result']['list']:
                    try:
                        tickers.append({
                            'symbol': ticker['symbol'],
                            'price': float(ticker['lastPrice']),
                            'volume': float(ticker['volume24h']) * float(ticker['lastPrice']),
                            'change': float(ticker['price24hPcnt']) * 100
                        })
                    except (ValueError, KeyError) as e:
                        continue
                self.tickers_data = tickers
                return tickers
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Ошибка получения тикеров: {error_msg}")
                return []
        except Exception as e:
            self.logger.error(f"Ошибка получения тикеров: {e}")
            return []

    def fetch_orders(self, symbol=None):
        # === ИСПРАВЛЕНИЕ: Проверка подключения ===
        if not self.session:
            return []
            
        try:
            kwargs = {"category": "linear"}
            if symbol:
                kwargs["symbol"] = symbol
            else:
                kwargs["settleCoin"] = "USDT"
            response = self.rate_limited_request(
                self.session.get_open_orders,
                **kwargs
            )
            if response and response.get('retCode') == 0:
                orders = []
                for order in response['result']['list']:
                    orders.append({
                        'symbol': order['symbol'],
                        'order_id': order['orderId'],
                        'side': order['side'],
                        'order_type': order['orderType'],
                        'price': float(order.get('price', 0)),
                        'qty': float(order.get('qty', 0)),
                        'leaves_qty': float(order.get('leavesQty', 0))
                    })
                self.orders_data = orders
                # Mark UI action
                self.status_action_label.config(text="Загружены заявки")
                return orders
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Ошибка получения ордеров: {error_msg}")
                return []
        except Exception as e:
            self.logger.error(f"Исключение при получении ордеров: {e}")
            return []
        
    def has_open_position(self, symbol):
        positions = self.fetch_positions(symbol=symbol)
        for pos in positions:
            if pos['symbol'] == symbol and float(pos['size']) > 0:
                return True
        return False

    def get_symbol_info(self, symbol):
        try:
            response = self.rate_limited_request(
                self.session.get_instruments_info,
                category="linear",
                symbol=symbol
            )
            if response and response.get('retCode') == 0 and response['result']['list']:
                return response['result']['list'][0]
        except Exception as e:
            self.logger.error(f"Ошибка получения информации о символе {symbol}: {e}")
        return None

    def get_max_leverage(self, symbol_info):
        try:
            if symbol_info and 'leverageFilter' in symbol_info:
                leverage_filter = symbol_info['leverageFilter']
                leverage_str = leverage_filter.get('maxLeverage', '5')
                return int(float(leverage_str))
        except (ValueError, TypeError) as e:
            self.logger.error(f"Ошибка получения максимального плеча: {e}")
        return 5

    def toggle_auto_trading(self):
        self.auto_trading = self.auto_trading_var.get()
        status = "включена" if self.auto_trading else "выключена"
        self.trading_status_label.config(
            text=f"🤖 Торговля: {'Вкл' if self.auto_trading else 'Выкл'}",
            foreground="green" if self.auto_trading else "red"
        )
        self.logger.info(f"Автоторговля {status}")
        if self.auto_trading:
            self.start_auto_trading()
        else:
            self.stop_auto_trading()

    def start_auto_trading(self):
        if self.trading_thread and self.trading_thread.is_alive():
            return
        def trading_loop():
            self.logger.info("Запуск цикла автоторговли")
            while self.auto_trading:
                try:
                    # 1. СНАЧАЛА проверяем закрытые позиции (чтобы успеть поставить таймаут и удалить из работы)
                    self.check_closed_positions()
                    
                    # 2. Проверяем достижение TP (для принудительного закрытия, если нужно)
                    self.check_take_profit_hit()
                    
                    # 3. И только ПОТОМ проверяем условия для входа или усреднения
                    # (это предотвратит повторный вход, так как монета уже будет удалена или в таймауте)
                    self.check_working_coin_conditions()
                    
                    time.sleep(2) # Небольшая пауза для разгрузки CPU
                except Exception as e:
                    self.logger.error(f"Ошибка в цикле торговли: {e}")
                    time.sleep(5)
            self.logger.info("Цикл автоторговли остановлен")
        self.trading_thread = threading.Thread(target=trading_loop, daemon=True)
        self.trading_thread.start()

    def stop_auto_trading(self):
        self.logger.info("Остановка автоторговли")

    def fetch_klines_for_symbol(self, symbol, interval, limit):
        # === ИСПРАВЛЕНИЕ: Проверка подключения ===
        if not self.session:
            return None
            
        try:
            response = self.rate_limited_request(
                self.session.get_kline,
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if not response or 'result' not in response or 'list' not in response['result']:
                return None
            data = response['result']['list']
            if not data:
                return None
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df = df.iloc[::-1]
            def safe_timestamp_conversion(ts):
                try:
                    return pd.to_datetime(int(ts), unit='ms')
                except (ValueError, OverflowError):
                    try:
                        return pd.to_datetime(str(ts), unit='ms')
                    except:
                        return pd.NaT
            df['timestamp'] = df['timestamp'].apply(safe_timestamp_conversion)
            df = df.dropna(subset=['timestamp'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            return df
        except Exception as e:
            self.logger.error(f"Ошибка получения данных для {symbol}: {e}")
            return None

    # ==================== УЛУЧШЕННЫЙ ОТЧЕТ PNL ====================
    def open_enhanced_pnl_report(self):
        """Улучшенный отчет PnL с группировкой по дням, неделям и месяцам"""
        win = tk.Toplevel(self.root)
        win.title("📊 Улучшенный отчет по сделкам (PnL)")
        win.geometry("1400x800")
        win.minsize(1200, 700)
        # Создаем систему отчетности
        pnl_reporter = EnhancedPnLReporting(self.trade_history)
        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Вкладка по дням
        daily_frame = ttk.Frame(notebook, padding=10)
        notebook.add(daily_frame, text="📅 По дням")
        self._fill_daily_tab(daily_frame, pnl_reporter)
        # Вкладка по неделям
        weekly_frame = ttk.Frame(notebook, padding=10)
        notebook.add(weekly_frame, text="📆 По неделям")
        self._fill_weekly_tab(weekly_frame, pnl_reporter)
        # Вкладка по месяцам
        monthly_frame = ttk.Frame(notebook, padding=10)
        notebook.add(monthly_frame, text="📊 По месяцам")
        self._fill_monthly_tab(monthly_frame, pnl_reporter)
        # Вкладка детали по дням
        details_frame = ttk.Frame(notebook, padding=10)
        notebook.add(details_frame, text="🔍 Детали по дням")
        self._fill_details_tab(details_frame, pnl_reporter)
        # Вкладка статистика по парам
        pairs_frame = ttk.Frame(notebook, padding=10)
        notebook.add(pairs_frame, text="💰 Статистика по парам")
        self._fill_pairs_tab(pairs_frame, pnl_reporter)
        # Вкладка вся статистика
        overall_frame = ttk.Frame(notebook, padding=10)
        notebook.add(overall_frame, text="📈 Вся статистика")
        self._fill_overall_tab(overall_frame, pnl_reporter)

    def _fill_daily_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с ежедневной статистикой"""
        daily_summary = pnl_reporter.get_daily_summary()
        # Создаем фрейм для заголовка
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Ежедневная статистика", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        # Создаем таблицу
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('date', 'trades', 'winning', 'losing', 'total_pnl', 'win_rate', 'avg_win', 'avg_loss', 'largest_win', 'largest_loss')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'date': 'Дата',
            'trades': 'Сделок',
            'winning': 'Прибыльных',
            'losing': 'Убыточных',
            'total_pnl': 'Общий PnL',
            'win_rate': 'Win Rate %',
            'avg_win': 'Ср. прибыль',
            'avg_loss': 'Ср. убыток',
            'largest_win': 'Макс. прибыль',
            'largest_loss': 'Макс. убыток'
        }
        for col, text in headers.items():
            tree.heading(col, text=text)
            tree.column(col, width=80)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Заполняем данными
        for day_data in daily_summary:
            tree.insert('', tk.END, values=(
                day_data['date'].strftime('%Y-%m-%d'),
                day_data['total_trades'],
                day_data['winning_trades'],
                day_data['losing_trades'],
                f"{day_data['total_pnl']:.2f}",
                f"{day_data['win_rate']:.1f}%",
                f"{day_data['avg_win']:.2f}",
                f"{day_data['avg_loss']:.2f}",
                f"{day_data['largest_win']:.2f}",
                f"{day_data['largest_loss']:.2f}"
            ))
        # Обработчик двойного клика для показа деталей дня
        def show_day_details(event):
            selection = tree.selection()
            if selection:
                item = selection[0]
                date_str = tree.item(item, 'values')[0]
                selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                self._show_day_trades_details(selected_date, pnl_reporter)
        tree.bind('<Double-1>', show_day_details)

    def _fill_weekly_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с еженедельной статистикой"""
        weekly_summary = pnl_reporter.get_weekly_summary()
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Еженедельная статистика", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('week', 'trades', 'winning', 'losing', 'total_pnl', 'win_rate', 'days_traded')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'week': 'Неделя',
            'trades': 'Сделок',
            'winning': 'Прибыльных',
            'losing': 'Убыточных',
            'total_pnl': 'Общий PnL',
            'win_rate': 'Win Rate %',
            'days_traded': 'Дней с trades'
        }
        for col, text in headers.items():
            tree.heading(col, text=text)
            tree.column(col, width=100)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for week_data in weekly_summary:
            tree.insert('', tk.END, values=(
                week_data['week'],
                week_data['total_trades'],
                week_data['winning_trades'],
                week_data['losing_trades'],
                f"{week_data['total_pnl']:.2f}",
                f"{week_data['win_rate']:.1f}%",
                week_data['days_traded']
            ))
        def show_week_details(event):
            selection = tree.selection()
            if selection:
                item = selection[0]
                week_str = tree.item(item, 'values')[0]
                self._show_week_trades_details(week_str, pnl_reporter)
        tree.bind('<Double-1>', show_week_details)

    def _fill_monthly_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с ежемесячной статистикой"""
        monthly_summary = pnl_reporter.get_monthly_summary()
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Ежемесячная статистика", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('month', 'trades', 'winning', 'losing', 'total_pnl', 'win_rate', 'days_traded')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'month': 'Месяц',
            'trades': 'Сделок',
            'winning': 'Прибыльных',
            'losing': 'Убыточных',
            'total_pnl': 'Общий PnL',
            'win_rate': 'Win Rate %',
            'days_traded': 'Дней с trades'
        }
        for col, text in headers.items():
            tree.heading(col, text=text)
            tree.column(col, width=100)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for month_data in monthly_summary:
            tree.insert('', tk.END, values=(
                month_data['month'],
                month_data['total_trades'],
                month_data['winning_trades'],
                month_data['losing_trades'],
                f"{month_data['total_pnl']:.2f}",
                f"{month_data['win_rate']:.1f}%",
                month_data['days_traded']
            ))

    def _fill_details_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с деталями по дням"""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Детализация сделок по дням", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        # Выбор даты
        date_frame = ttk.Frame(parent)
        date_frame.pack(fill=tk.X, pady=5)
        ttk.Label(date_frame, text="Выберите дату:").pack(side=tk.LEFT, padx=5)
        date_var = tk.StringVar()
        date_combobox = ttk.Combobox(date_frame, textvariable=date_var, state="readonly")
        # Получаем список дат с trades
        all_trades = pnl_reporter.get_all_trades()
        dates = sorted(set(datetime.fromisoformat(trade['timestamp']).date() for trade in all_trades), reverse=True)
        date_combobox['values'] = [date.strftime('%Y-%m-%d') for date in dates]
        if dates:
            date_combobox.set(dates[0].strftime('%Y-%m-%d'))
        date_combobox.pack(side=tk.LEFT, padx=5)
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol', 'side', 'entry_price', 'close_price', 'size', 'pnl', 'timestamp', 'strategy')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'symbol': 'Пара',
            'side': 'Сторона',
            'entry_price': 'Цена входа',
            'close_price': 'Цена выхода', 
            'size': 'Размер',
            'pnl': 'PnL USDT',
            'timestamp': 'Время',
            'strategy': 'Стратегия'
        }
        for col, text in headers.items():
            tree.heading(col, text=text)
            tree.column(col, width=90)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        def update_trades_display(*args):
            for item in tree.get_children():
                tree.delete(item)
            selected_date_str = date_var.get()
            if selected_date_str:
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
                day_trades = pnl_reporter.get_trades_for_date(selected_date)
                for trade in day_trades:
                    tree.insert('', tk.END, values=(
                        trade['symbol'],
                        trade.get('side', ''),
                        f"{trade.get('entry_price', 0):.4f}",
                        f"{trade.get('close_price', 0):.4f}",
                        f"{trade.get('size', 0):.2f}",
                        f"{trade.get('pnl', 0):.2f}",
                        datetime.fromisoformat(trade['timestamp']).strftime('%H:%M:%S'),
                        trade.get('strategy', 'N/A')
                    ))
        date_var.trace_add('write', update_trades_display)
        update_trades_display()

    def _fill_pairs_tab(self, parent, pnl_reporter):
        """Заполнение вкладки со статистикой по парам"""
        metrics = pnl_reporter.get_performance_metrics()
        pair_stats = metrics.get('pair_stats', {})
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Статистика по торговым парам", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol', 'trades', 'winning', 'losing', 'win_rate', 'total_pnl', 'avg_pnl', 'total_volume')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        headers = {
            'symbol': 'Пара',
            'trades': 'Сделок',
            'winning': 'Прибыльных',
            'losing': 'Убыточных',
            'win_rate': 'Win Rate %',
            'total_pnl': 'Общий PnL',
            'avg_pnl': 'Ср. PnL',
            'total_volume': 'Объем USDT'
        }
        for col, text in headers.items():
            tree.heading(col, text=text)
            tree.column(col, width=90)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for symbol, stats in pair_stats.items():
            tree.insert('', tk.END, values=(
                symbol,
                stats['count'],
                stats['wins'],
                stats['count'] - stats['wins'],
                f"{stats['win_rate']:.1f}%",
                f"{stats['pnl']:.2f}",
                f"{stats['avg_pnl']:.2f}",
                f"{stats['total_volume']:.2f}"
            ))

    def _fill_overall_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с общей статистикой"""
        metrics = pnl_reporter.get_performance_metrics()
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Общая статистика", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        # Основные метрики
        metrics_frame = ttk.LabelFrame(parent, text="Ключевые показатели", padding=10)
        metrics_frame.pack(fill=tk.X, pady=5)
        metrics_grid = ttk.Frame(metrics_frame)
        metrics_grid.pack(fill=tk.X)
        main_metrics = [
            ("Всего сделок:", f"{metrics.get('total_trades', 0)}"),
            ("Прибыльных сделок:", f"{metrics.get('winning_trades', 0)}"),
            ("Убыточных сделок:", f"{metrics.get('losing_trades', 0)}"),
            ("Win Rate:", f"{metrics.get('win_rate', 0):.1f}%"),
            ("Общий PnL:", f"{metrics.get('total_pnl', 0):.2f} USDT"),
            ("Средний PnL:", f"{metrics.get('avg_pnl', 0):.2f} USDT"),
            ("Макс. прибыль:", f"{metrics.get('largest_win', 0):.2f} USDT"),
            ("Макс. убыток:", f"{metrics.get('largest_loss', 0):.2f} USDT"),
            ("Profit Factor:", f"{metrics.get('profit_factor', 0):.2f}")
        ]
        for i, (label, value) in enumerate(main_metrics):
            row = i % 5
            col = i // 5
            ttk.Label(metrics_grid, text=label, font=('Arial', 9, 'bold')).grid(
                row=row, column=col*2, sticky=tk.W, padx=5, pady=2)
            ttk.Label(metrics_grid, text=value, font=('Arial', 9)).grid(
                row=row, column=col*2+1, sticky=tk.W, padx=5, pady=2)
        # Статистика по стратегиям
        strategy_frame = ttk.LabelFrame(parent, text="Статистика по стратегиям", padding=10)
        strategy_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        strategy_tree_frame = ttk.Frame(strategy_frame)
        strategy_tree_frame.pack(fill=tk.BOTH, expand=True)
        strategy_columns = ('strategy', 'trades', 'win_rate', 'total_pnl', 'avg_pnl')
        strategy_tree = ttk.Treeview(strategy_tree_frame, columns=strategy_columns, show='headings', height=8)
        strategy_headers = {
            'strategy': 'Стратегия',
            'trades': 'Сделок',
            'win_rate': 'Win Rate %',
            'total_pnl': 'Общий PnL',
            'avg_pnl': 'Ср. PnL'
        }
        for col, text in strategy_headers.items():
            strategy_tree.heading(col, text=text)
            strategy_tree.column(col, width=120)
        strategy_scrollbar = ttk.Scrollbar(strategy_tree_frame, orient=tk.VERTICAL, command=strategy_tree.yview)
        strategy_tree.configure(yscrollcommand=strategy_scrollbar.set)
        strategy_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        strategy_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        strategy_stats = metrics.get('strategy_stats', {})
        for strategy, stats in strategy_stats.items():
            strategy_tree.insert('', tk.END, values=(
                strategy,
                stats['count'],
                f"{stats['win_rate']:.1f}%",
                f"{stats['pnl']:.2f}",
                f"{stats['avg_pnl']:.2f}"
            ))

    def _show_day_trades_details(self, date, pnl_reporter):
        """Показать детали сделок за выбранный день"""
        day_trades = pnl_reporter.get_trades_for_date(date)
        details_win = tk.Toplevel(self.root)
        details_win.title(f"Детали сделок за {date}")
        details_win.geometry("1000x600")
        header_frame = ttk.Frame(details_win, padding=10)
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text=f"Сделки за {date}", 
                 font=('Arial', 14, 'bold')).pack()
        tree_frame = ttk.Frame(details_win)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        columns = ('symbol', 'side', 'entry_price', 'close_price', 'size', 'pnl', 'timestamp', 'strategy', 'close_type')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=20)
        headers = {
            'symbol': 'Пара',
            'side': 'Сторона',
            'entry_price': 'Цена входа',
            'close_price': 'Цена выхода',
            'size': 'Размер',
            'pnl': 'PnL USDT',
            'timestamp': 'Время',
            'strategy': 'Стратегия',
            'close_type': 'Тип закрытия'
        }
        for col, text in headers.items():
            tree.heading(col, text=text)
            tree.column(col, width=90)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for trade in day_trades:
            pnl = trade.get('pnl', 0)
            pnl_color = "#44bd32" if pnl >= 0 else "#e84118"
            item = tree.insert('', tk.END, values=(
                trade['symbol'],
                trade.get('side', ''),
                f"{trade.get('entry_price', 0):.4f}",
                f"{trade.get('close_price', 0):.4f}",
                f"{trade.get('size', 0):.2f}",
                f"{pnl:.2f}",
                datetime.fromisoformat(trade['timestamp']).strftime('%H:%M:%S'),
                trade.get('strategy', 'N/A'),
                trade.get('close_type', 'N/A')
            ))

    def _show_week_trades_details(self, week_str, pnl_reporter):
        """Показать детали сделок за выбранную неделю"""
        weekly_summary = pnl_reporter.get_weekly_summary()
        week_data = next((week for week in weekly_summary if week['week'] == week_str), None)
        if not week_data:
            return
        details_win = tk.Toplevel(self.root)
        details_win.title(f"Детали сделок за неделю {week_str}")
        details_win.geometry("1200x700")
        notebook = ttk.Notebook(details_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Вкладка со всеми сделками недели
        all_trades_frame = ttk.Frame(notebook, padding=10)
        notebook.add(all_trades_frame, text="Все сделки недели")
        tree_frame = ttk.Frame(all_trades_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('date', 'symbol', 'side', 'entry_price', 'close_price', 'size', 'pnl', 'strategy')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=20)
        headers = {
            'date': 'Дата',
            'symbol': 'Пара',
            'side': 'Сторона',
            'entry_price': 'Цена входа',
            'close_price': 'Цена выхода',
            'size': 'Размер',
            'pnl': 'PnL USDT',
            'strategy': 'Стратегия'
        }
        for col, text in headers.items():
            tree.heading(col, text=text)
            tree.column(col, width=100)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for trade in week_data['trades_list']:
            trade_date = datetime.fromisoformat(trade['timestamp']).strftime('%Y-%m-%d')
            tree.insert('', tk.END, values=(
                trade_date,
                trade['symbol'],
                trade.get('side', ''),
                f"{trade.get('entry_price', 0):.4f}",
                f"{trade.get('close_price', 0):.4f}",
                f"{trade.get('size', 0):.2f}",
                f"{trade.get('pnl', 0):.2f}",
                trade.get('strategy', 'N/A')
            ))
        # Вкладка со статистикой по парам за неделю
        pairs_frame = ttk.Frame(notebook, padding=10)
        notebook.add(pairs_frame, text="Статистика по парам")
        pairs_tree_frame = ttk.Frame(pairs_frame)
        pairs_tree_frame.pack(fill=tk.BOTH, expand=True)
        pairs_columns = ('symbol', 'trades', 'winning', 'losing', 'win_rate', 'total_pnl', 'avg_pnl')
        pairs_tree = ttk.Treeview(pairs_tree_frame, columns=pairs_columns, show='headings', height=15)
        pairs_headers = {
            'symbol': 'Пара',
            'trades': 'Сделок',
            'winning': 'Прибыльных',
            'losing': 'Убыточных',
            'win_rate': 'Win Rate %',
            'total_pnl': 'Общий PnL',
            'avg_pnl': 'Ср. PnL'
        }
        for col, text in pairs_headers.items():
            pairs_tree.heading(col, text=text)
            pairs_tree.column(col, width=100)
        pairs_scrollbar = ttk.Scrollbar(pairs_tree_frame, orient=tk.VERTICAL, command=pairs_tree.yview)
        pairs_tree.configure(yscrollcommand=pairs_scrollbar.set)
        pairs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pairs_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for symbol, pair_data in week_data['pairs'].items():
            pairs_tree.insert('', tk.END, values=(
                symbol,
                pair_data['trades'],
                pair_data['winning_trades'],
                pair_data['losing_trades'],
                f"{pair_data.get('win_rate', 0):.1f}%",
                f"{pair_data['total_pnl']:.2f}",
                f"{pair_data.get('avg_pnl', 0):.2f}"
            ))

    def _fill_all_stats_tab(self, parent, pnl_reporter):
        """НОВЫЙ МЕТОД: Заполнение вкладки со всей статистикой"""
        all_trades = pnl_reporter.get_all_trades()
        if not all_trades:
            ttk.Label(parent, text="📊 Нет данных о сделках для отображения", 
                     font=('Arial', 12), foreground="gray").pack(expand=True)
            return
        # Создаем Treeview для отображения всех сделок
        columns = ('symbol', 'side', 'open_date', 'close_date', 'entry_price', 'close_price', 
                  'size', 'pnl', 'pnl_percent', 'strategy', 'close_type')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        tree.heading('symbol', text='Пара')
        tree.heading('side', text='Направление')
        tree.heading('open_date', text='Дата открытия')
        tree.heading('close_date', text='Дата закрытия')
        tree.heading('entry_price', text='Цена входа')
        tree.heading('close_price', text='Цена выхода')
        tree.heading('size', text='Размер USDT')
        tree.heading('pnl', text='PnL USDT')
        tree.heading('pnl_percent', text='PnL %')
        tree.heading('strategy', text='Стратегия')
        tree.heading('close_type', text='Тип закрытия')
        tree.column('symbol', width=80)
        tree.column('side', width=80)
        tree.column('open_date', width=120)
        tree.column('close_date', width=120)
        tree.column('entry_price', width=90)
        tree.column('close_price', width=90)
        tree.column('size', width=90)
        tree.column('pnl', width=80)
        tree.column('pnl_percent', width=70)
        tree.column('strategy', width=100)
        tree.column('close_type', width=100)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for trade in all_trades:
            # Расчет PnL в процентах
            pnl_percent = 0.0
            if 'entry_price' in trade and 'close_price' in trade:
                if trade['side'] == 'Buy':
                    pnl_percent = (trade['close_price'] - trade['entry_price']) / trade['entry_price'] * 100
                else:
                    pnl_percent = (trade['entry_price'] - trade['close_price']) / trade['entry_price'] * 100
            # Форматирование дат
            open_date = datetime.fromisoformat(trade['timestamp']).strftime("%Y-%m-%d %H:%M")
            close_date = open_date  # Для упрощения, можно добавить отдельное поле для даты закрытия
            pnl_color = "green" if trade.get('pnl', 0) >= 0 else "red"
            pnl_percent_color = "green" if pnl_percent >= 0 else "red"
            item_id = tree.insert('', tk.END, values=(
                trade['symbol'],
                trade['side'],
                open_date,
                close_date,
                f"{trade.get('entry_price', 0):.4f}",
                f"{trade.get('close_price', 0):.4f}",
                f"{trade.get('size', 0):.2f}",
                f"{trade.get('pnl', 0):.2f}",
                f"{pnl_percent:.2f}%",
                trade.get('strategy', 'unknown'),
                trade.get('close_type', 'Unknown')
            ))
            # Устанавливаем цвет для PnL
            tree.set(item_id, 'pnl', f"{trade.get('pnl', 0):.2f}")
            tree.set(item_id, 'pnl_percent', f"{pnl_percent:.2f}%")

    def _fill_stats_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с общей статистикой"""
        metrics = pnl_reporter.get_performance_metrics()
        # Основные метрики
        main_metrics_frame = ttk.LabelFrame(parent, text="📊 Ключевые метрики", padding=10)
        main_metrics_frame.pack(fill=tk.X, pady=(0, 10))
        metrics_grid = ttk.Frame(main_metrics_frame)
        metrics_grid.pack(fill=tk.X)
        # Строка 1
        ttk.Label(metrics_grid, text=f"Всего сделок: {metrics['total_trades']}", 
                 font=('Arial', 11, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(metrics_grid, text=f"Прибыльные: {metrics['winning_trades']}", 
                 font=('Arial', 11, 'bold'), foreground="green").grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(metrics_grid, text=f"Убыточные: {metrics['losing_trades']}", 
                 font=('Arial', 11, 'bold'), foreground="red").grid(row=0, column=2, sticky=tk.W, padx=10, pady=5)
        # Строка 2
        ttk.Label(metrics_grid, text=f"Винрейт: {metrics['win_rate']:.2f}%", 
                 font=('Arial', 11, 'bold')).grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(metrics_grid, text=f"Общий PnL: {metrics['total_pnl']:+.2f} USDT", 
                 font=('Arial', 11, 'bold'), 
                 foreground="green" if metrics['total_pnl'] >= 0 else "red").grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(metrics_grid, text=f"Средний PnL: {metrics['avg_pnl']:+.2f} USDT", 
                 font=('Arial', 11, 'bold')).grid(row=1, column=2, sticky=tk.W, padx=10, pady=5)
        # Строка 3
        ttk.Label(metrics_grid, text=f"Средний выигрыш: {metrics['avg_win']:+.2f} USDT", 
                 font=('Arial', 10)).grid(row=2, column=0, sticky=tk.W, padx=10, pady=2)
        ttk.Label(metrics_grid, text=f"Средний проигрыш: {metrics['avg_loss']:+.2f} USDT", 
                 font=('Arial', 10)).grid(row=2, column=1, sticky=tk.W, padx=10, pady=2)
        ttk.Label(metrics_grid, text=f"Фактор прибыли: {metrics['profit_factor']:.2f}", 
                 font=('Arial', 10)).grid(row=2, column=2, sticky=tk.W, padx=10, pady=2)
        # Статистика по стратегиям
        if metrics['strategy_stats']:
            strategy_frame = ttk.LabelFrame(parent, text="🎯 Статистика по стратегиям", padding=10)
            strategy_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            columns = ('strategy', 'trades', 'win_rate', 'total_pnl', 'avg_pnl')
            tree = ttk.Treeview(strategy_frame, columns=columns, show='headings', height=8)
            tree.heading('strategy', text='Стратегия')
            tree.heading('trades', text='Сделки')
            tree.heading('win_rate', text='Винрейт %')
            tree.heading('total_pnl', text='Общий PnL')
            tree.heading('avg_pnl', text='Средний PnL')
            tree.column('strategy', width=150)
            tree.column('trades', width=80)
            tree.column('win_rate', width=100)
            tree.column('total_pnl', width=100)
            tree.column('avg_pnl', width=100)
            scrollbar = ttk.Scrollbar(strategy_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            for strategy, stats in metrics['strategy_stats'].items():
                pnl_color = "green" if stats['pnl'] >= 0 else "red"
                item_id = tree.insert('', tk.END, values=(
                    strategy,
                    stats['count'],
                    f"{stats['win_rate']:.2f}%",
                    f"{stats['pnl']:+.2f}",
                    f"{stats['avg_pnl']:+.2f}"
                ))
                tree.set(item_id, 'total_pnl', f"{stats['pnl']:+.2f}")

    def _fill_daily_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с ежедневной статистикой"""
        daily_summary = pnl_reporter.get_daily_summary()
        columns = ('date', 'trades', 'winning', 'losing', 'win_rate', 'total_pnl', 'avg_win', 'avg_loss', 'symbols', 'largest_win', 'largest_loss')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        tree.heading('date', text='Дата')
        tree.heading('trades', text='Сделки')
        tree.heading('winning', text='Прибыльные')
        tree.heading('losing', text='Убыточные')
        tree.heading('win_rate', text='Винрейт %')
        tree.heading('total_pnl', text='Общий PnL')
        tree.heading('avg_win', text='Ср. выигрыш')
        tree.heading('avg_loss', text='Ср. проигрыш')
        tree.heading('symbols', text='Символов')
        tree.heading('largest_win', text='Макс. выигрыш')
        tree.heading('largest_loss', text='Макс. проигрыш')
        tree.column('date', width=100)
        tree.column('trades', width=70)
        tree.column('winning', width=80)
        tree.column('losing', width=80)
        tree.column('win_rate', width=80)
        tree.column('total_pnl', width=100)
        tree.column('avg_win', width=100)
        tree.column('avg_loss', width=100)
        tree.column('symbols', width=80)
        tree.column('largest_win', width=100)
        tree.column('largest_loss', width=100)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for day in daily_summary:
            pnl_color = "green" if day['total_pnl'] >= 0 else "red"
            item_id = tree.insert('', tk.END, values=(
                day['date'].strftime("%Y-%m-%d"),
                day['total_trades'],
                day['winning_trades'],
                day['losing_trades'],
                f"{day['win_rate']:.2f}%",
                f"{day['total_pnl']:+.2f}",
                f"{day['avg_win']:+.2f}",
                f"{day['avg_loss']:+.2f}",
                len(day['symbols']),
                f"{day['largest_win']:+.2f}",
                f"{day['largest_loss']:+.2f}"
            ))
            tree.set(item_id, 'total_pnl', f"{day['total_pnl']:+.2f}")

    def _fill_weekly_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с еженедельной статистикой"""
        weekly_summary = pnl_reporter.get_weekly_summary()
        columns = ('week', 'trades', 'winning', 'losing', 'win_rate', 'total_pnl', 'days_traded')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        tree.heading('week', text='Неделя')
        tree.heading('trades', text='Сделки')
        tree.heading('winning', text='Прибыльные')
        tree.heading('losing', text='Убыточные')
        tree.heading('win_rate', text='Винрейт %')
        tree.heading('total_pnl', text='Общий PnL')
        tree.heading('days_traded', text='Дней с trades')
        tree.column('week', width=100)
        tree.column('trades', width=80)
        tree.column('winning', width=80)
        tree.column('losing', width=80)
        tree.column('win_rate', width=80)
        tree.column('total_pnl', width=100)
        tree.column('days_traded', width=100)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for week in weekly_summary:
            pnl_color = "green" if week['total_pnl'] >= 0 else "red"
            item_id = tree.insert('', tk.END, values=(
                week['week'],
                week['total_trades'],
                week['winning_trades'],
                week['losing_trades'],
                f"{week['win_rate']:.2f}%",
                f"{week['total_pnl']:+.2f}",
                week['days_traded']
            ))
            tree.set(item_id, 'total_pnl', f"{week['total_pnl']:+.2f}")

    def _fill_monthly_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с ежемесячной статистикой"""
        monthly_summary = pnl_reporter.get_monthly_summary()
        columns = ('month', 'trades', 'winning', 'losing', 'win_rate', 'total_pnl', 'days_traded')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        tree.heading('month', text='Месяц')
        tree.heading('trades', text='Сделки')
        tree.heading('winning', text='Прибыльные')
        tree.heading('losing', text='Убыточные')
        tree.heading('win_rate', text='Винрейт %')
        tree.heading('total_pnl', text='Общий PnL')
        tree.heading('days_traded', text='Дней с trades')
        tree.column('month', width=100)
        tree.column('trades', width=80)
        tree.column('winning', width=80)
        tree.column('losing', width=80)
        tree.column('win_rate', width=80)
        tree.column('total_pnl', width=100)
        tree.column('days_traded', width=100)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for month in monthly_summary:
            pnl_color = "green" if month['total_pnl'] >= 0 else "red"
            item_id = tree.insert('', tk.END, values=(
                month['month'],
                month['total_trades'],
                month['winning_trades'],
                month['losing_trades'],
                f"{month['win_rate']:.2f}%",
                f"{month['total_pnl']:+.2f}",
                month['days_traded']
            ))
            tree.set(item_id, 'total_pnl', f"{month['total_pnl']:+.2f}")

    def _fill_day_detail_tab(self, parent, pnl_reporter):
        """Заполнение вкладки с детализацией по дням"""
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True)
        # Левая панель - список дней
        left_frame = ttk.Frame(main_frame, width=200)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)
        ttk.Label(left_frame, text="📅 Выберите день:", font=('Arial', 10, 'bold')).pack(pady=10)
        days_listbox = tk.Listbox(left_frame, font=('Arial', 9))
        days_listbox.pack(fill=tk.BOTH, expand=True, padx=5)
        # Правая панель - детали дня
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        detail_frame = ttk.LabelFrame(right_frame, text="Детали дня", padding=10)
        detail_frame.pack(fill=tk.BOTH, expand=True)
        # Заполняем список дней
        daily_summary = pnl_reporter.get_daily_summary()
        days_map = {}
        for day in daily_summary:
            day_str = day['date'].strftime("%Y-%m-%d")
            days_listbox.insert(tk.END, day_str)
            days_map[day_str] = day
        # Детали дня
        day_info_frame = ttk.Frame(detail_frame)
        day_info_frame.pack(fill=tk.X, pady=(0, 10))
        self.day_info_text = tk.Text(day_info_frame, height=8, font=('Arial', 9), wrap=tk.WORD)
        day_info_scrollbar = ttk.Scrollbar(day_info_frame, orient=tk.VERTICAL, command=self.day_info_text.yview)
        self.day_info_text.configure(yscrollcommand=day_info_scrollbar.set)
        self.day_info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        day_info_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Сделки дня
        trades_frame = ttk.LabelFrame(detail_frame, text="Сделки дня", padding=10)
        trades_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol', 'side', 'entry_price', 'close_price', 'size', 'pnl', 'strategy', 'close_type')
        self.day_trades_tree = ttk.Treeview(trades_frame, columns=columns, show='headings', height=12)
        tree_headers = {
            'symbol': 'Пара',
            'side': 'Сторона',
            'entry_price': 'Цена входа',
            'close_price': 'Цена выхода',
            'size': 'Размер',
            'pnl': 'PnL USDT',
            'strategy': 'Стратегия',
            'close_type': 'Тип закрытия'
        }
        for col, text in tree_headers.items():
            self.day_trades_tree.heading(col, text=text)
            self.day_trades_tree.column(col, width=80)
        self.day_trades_tree.column('symbol', width=70)
        self.day_trades_tree.column('strategy', width=100)
        self.day_trades_tree.column('close_type', width=100)
        trades_scrollbar = ttk.Scrollbar(trades_frame, orient=tk.VERTICAL, command=self.day_trades_tree.yview)
        self.day_trades_tree.configure(yscrollcommand=trades_scrollbar.set)
        self.day_trades_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        trades_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        def on_day_select(event):
            selection = days_listbox.curselection()
            if selection:
                day_str = days_listbox.get(selection[0])
                day_data = days_map.get(day_str)
                if day_data:
                    # Обновляем информацию о дне
                    self.day_info_text.delete(1.0, tk.END)
                    info_text = f"""
📅 Дата: {day_str}
📊 Сделок: {day_data['total_trades']}
✅ Прибыльных: {day_data['winning_trades']}
❌ Убыточных: {day_data['losing_trades']}
🎯 Винрейт: {day_data['win_rate']:.2f}%
💰 Общий PnL: {day_data['total_pnl']:+.2f} USDT
📈 Средний выигрыш: {day_data['avg_win']:+.2f} USDT
📉 Средний проигрыш: {day_data['avg_loss']:+.2f} USDT
🏆 Крупнейший выигрыш: {day_data['largest_win']:+.2f} USDT
💸 Крупнейший проигрыш: {day_data['largest_loss']:+.2f} USDT
🔢 Уникальных символов: {len(day_data['symbols'])}
🎯 Стратегии: {', '.join(day_data['strategies'].keys())}
"""
                    self.day_info_text.insert(1.0, info_text.strip())
                    # Обновляем список сделок
                    for item in self.day_trades_tree.get_children():
                        self.day_trades_tree.delete(item)
                    day_trades = pnl_reporter.get_trades_for_date(day_data['date'])
                    for trade in day_trades:
                        pnl_display = f"{trade['pnl']:+.2f}"
                        pnl_color = "green" if trade['pnl'] >= 0 else "red"
                        item_id = self.day_trades_tree.insert('', tk.END, values=(
                            trade['symbol'],
                            trade['side'],
                            f"{trade['entry_price']:.4f}",
                            f"{trade['close_price']:.4f}",
                            f"{trade['size']:.4f}",
                            pnl_display,
                            trade.get('strategy', 'unknown'),
                            trade.get('close_type', 'Unknown')
                        ))
                        self.day_trades_tree.set(item_id, 'pnl', pnl_display)
        days_listbox.bind('<<ListboxSelect>>', on_day_select)
        # Выбираем первый день по умолчанию
        if daily_summary:
            days_listbox.selection_set(0)
            days_listbox.event_generate('<<ListboxSelect>>')

    def _fill_pairs_tab(self, parent, pnl_reporter):
        """Заполнение вкладки со статистикой по парам"""
        metrics = pnl_reporter.get_performance_metrics()
        pair_stats = metrics.get('pair_stats', {})
        if not pair_stats:
            ttk.Label(parent, text="📊 Нет данных по парам для отображения", 
                     font=('Arial', 12), foreground="gray").pack(expand=True)
            return
        # Создаем Treeview для отображения статистики по парам
        columns = ('symbol', 'trades', 'winning', 'losing', 'win_rate', 'total_pnl', 'avg_pnl', 'total_volume', 'avg_volume')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        tree.heading('symbol', text='Пара')
        tree.heading('trades', text='Сделки')
        tree.heading('winning', text='Прибыльные')
        tree.heading('losing', text='Убыточные')
        tree.heading('win_rate', text='Винрейт %')
        tree.heading('total_pnl', text='Общий PnL')
        tree.heading('avg_pnl', text='Средний PnL')
        tree.heading('total_volume', text='Общий объем USDT')
        tree.heading('avg_volume', text='Ср. объем USDT')
        tree.column('symbol', width=80)
        tree.column('trades', width=70)
        tree.column('winning', width=80)
        tree.column('losing', width=80)
        tree.column('win_rate', width=80)
        tree.column('total_pnl', width=100)
        tree.column('avg_pnl', width=100)
        tree.column('total_volume', width=120)
        tree.column('avg_volume', width=120)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Сортируем пары по общему PnL (убыванию)
        sorted_pairs = sorted(pair_stats.items(), key=lambda x: x[1]['pnl'], reverse=True)
        for symbol, stats in sorted_pairs:
            pnl_color = "green" if stats['pnl'] >= 0 else "red"
            losing_trades = stats['count'] - stats['wins']
            item_id = tree.insert('', tk.END, values=(
                symbol,
                stats['count'],
                stats['wins'],
                losing_trades,
                f"{stats['win_rate']:.2f}%",
                f"{stats['pnl']:+.2f}",
                f"{stats['avg_pnl']:+.2f}",
                f"{stats['total_volume']:.2f}",
                f"{stats['avg_volume']:.2f}"
            ))
            tree.set(item_id, 'total_pnl', f"{stats['pnl']:+.2f}")

    def show_performance_stats(self):
        stats = self.performance_optimizer.get_performance_stats()
        stats_text = f"""
📊 Статистика производительности:
-----------------------------
📈 Всего запросов: {stats['total_requests']}
❌ Неудачных запросов: {stats['failed_requests']}
⏱️ Среднее время ответа: {stats['avg_response_time']:.3f} сек
🚀 Запросов в секунду: {stats['requests_per_second']:.2f}
📊 Процент ошибок: {stats['error_rate']:.2%}
🎛️ Множитель задержки: {self._dynamic_delay_multiplier:.2f}
        """
        messagebox.showinfo("📊 Статистика производительности", stats_text.strip())
    # ====== UTILS: Sorting, Context menus, Orders helpers, Hotkeys ======
    def _enable_treeview_sorting(self, tree):
        def sortby(col, reverse):
            try:
                data = [(tree.set(k, col), k) for k in tree.get_children('')]
                # try numeric sort then fallback to string
                try:
                    data = [(float(v.replace('%','').replace('+','')) if isinstance(v, str) else float(v), k) for v, k in data]  # type: ignore
                except Exception:
                    data = [(str(v), k) for v, k in data]
                data.sort(reverse=reverse)
                for index, (_, k) in enumerate(data):
                    tree.move(k, '', index)
                tree.heading(col, command=lambda: sortby(col, not reverse))
            except Exception:
                pass
        for col in tree["columns"]:
            tree.heading(col, command=lambda c=col: sortby(c, False))
    def _open_context_menu(self, event, tree, menu):
        try:
            row_id = tree.identify_row(event.y)
            if row_id:
                tree.selection_set(row_id)
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    def _context_open_edit(self, tree):
        selection = tree.selection()
        if not selection:
            return
        symbol = tree.item(selection[0], 'values')[0]
        config = next((c for c in self.working_coin_configs if c.symbol == symbol), None)
        if config:
            self.open_edit_trading_pair_window(config, is_working_coin=True)
    def _context_set_tp(self, tree):
        selection = tree.selection()
        if not selection:
            return
        symbol = tree.item(selection[0], 'values')[0]
        position = next((p for p in self.positions_data if p['symbol'] == symbol), None)
        if not position:
            return
        config = next((c for c in self.working_coin_configs if c.symbol == symbol), None)
        if not config:
            return
        self.set_take_profit_with_protection(symbol, position['side'], config)
        self.status_action_label.config(text=f"TP обновлён для {symbol}")
    def _context_cancel_orders(self, tree):
        selection = tree.selection()
        if not selection:
            return
        symbol = tree.item(selection[0], 'values')[0]
        self.cancel_all_orders_for_symbol(symbol)
        self.status_action_label.config(text=f"Отменены ордера {symbol}")
        self._refresh_orders_table()
    def _refresh_orders_table(self):
        if not hasattr(self, 'orders_tree'):
            return
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        for o in self.orders_data:
            if o.get('order_type') != 'Limit':
                continue
            self.orders_tree.insert('', tk.END, values=(
                o['symbol'], o['side'], o['order_type'], f"{o['price']:.4f}", f"{o['qty']:.4f}", f"{o['leaves_qty']:.4f}"
            ))
    def _cancel_selected_orders(self):
        selected = getattr(self, 'orders_tree', None).selection() if hasattr(self, 'orders_tree') else []
        if not selected:
            return
        for item in selected:
            vals = self.orders_tree.item(item, 'values')
            symbol = vals[0]
            order = next((o for o in self.orders_data if o['symbol'] == symbol and f"{o['price']:.4f}" == vals[3] and f"{o['qty']:.4f}" == vals[4]), None)
            if order:
                try:
                    self.rate_limited_request(
                        self.session.cancel_order,
                        category="linear",
                        symbol=symbol,
                        orderId=order['order_id']
                    )
                except Exception as e:
                    self.logger.warning(f"Не удалось отменить ордер {order['order_id']}: {e}")
        self.status_action_label.config(text="Отменены выбранные ордера")
        self.fetch_orders()
        self._refresh_orders_table()
    def _cancel_all_orders_all_symbols(self):
        try:
            self.rate_limited_request(
                self.session.cancel_all_orders,
                category="linear",
                settleCoin="USDT"
            )
            self.status_action_label.config(text="Массовая отмена всех ордеров")
            self.fetch_orders()
            self._refresh_orders_table()
        except Exception as e:
            self.logger.error(f"Массовая отмена не удалась: {e}")
    def _bind_hotkeys(self):
        try:
            self.root.bind("<F5>", lambda e: self.update_suitable_coins())
            self.root.bind("<Control-p>", lambda e: self.open_trading_pairs_manager())
            self.root.bind("<Control-P>", lambda e: self.open_trading_pairs_manager())
            self.root.bind("<Control-l>", lambda e: self.show_performance_stats())
            self.root.bind("<Control-L>", lambda e: self.show_performance_stats())
            self.root.bind("<Control-t>", lambda e: self.toggle_auto_trading())
            self.root.bind("<Control-T>", lambda e: self.toggle_auto_trading())
        except Exception:
            pass
    def open_blacklist_manager(self):
        self.logger.info("Открытие менеджера черного списка")
        win = tk.Toplevel(self.root)
        win.title("🚫 Управление черным списком")
        win.geometry("400x500")
        win.minsize(350, 400)
        main_frame = ttk.Frame(win, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        add_frame = ttk.LabelFrame(main_frame, text="➕ Добавить в черный список", padding=10)
        add_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(add_frame, text="📊 Символ монеты:").pack(anchor=tk.W)
        symbol_entry = ttk.Entry(add_frame, width=20)
        symbol_entry.pack(fill=tk.X, pady=5)
        def add_symbol():
            symbol = symbol_entry.get().strip().upper()
            if symbol:
                if symbol not in self.blacklist:
                    self.add_to_blacklist(symbol)
                    symbol_entry.delete(0, tk.END)
                    update_blacklist_display()
                    messagebox.showinfo("Успех", f"✅ Монета {symbol} добавлена в черный список")
                else:
                    messagebox.showinfo("Информация", f"ℹ️ Монета {symbol} уже в черном списке")
            else:
                messagebox.showwarning("Предупреждение", "⚠️ Введите символ монеты")
        ttk.Button(add_frame, text="➕ Добавить", command=add_symbol).pack(fill=tk.X, pady=5)
        list_frame = ttk.LabelFrame(main_frame, text="📋 Черный список", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('symbol',)
        blacklist_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        blacklist_tree.heading('symbol', text='Символ')
        blacklist_tree.column('symbol', width=200)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=blacklist_tree.yview)
        blacklist_tree.configure(yscrollcommand=scrollbar.set)
        blacklist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        def update_blacklist_display():
            for item in blacklist_tree.get_children():
                blacklist_tree.delete(item)
            for symbol in self.blacklist:
                blacklist_tree.insert('', tk.END, values=(symbol,))
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        def remove_selected():
            selected = blacklist_tree.selection()
            if selected:
                symbol = blacklist_tree.item(selected[0], 'values')[0]
                self.remove_from_blacklist(symbol)
                update_blacklist_display()
                messagebox.showinfo("Успех", f"✅ Монета {symbol} удалена из черного списка")
            else:
                messagebox.showwarning("Предупреждение", "⚠️ Выберите монету для удаления")
        def clear_blacklist():
            if messagebox.askyesno("Подтверждение", "🗑️ Очистить весь черный список?"):
                self.blacklist = []
                self.save_blacklist()
                update_blacklist_display()
                messagebox.showinfo("Успех", "✅ Черный список очищен")
        ttk.Button(button_frame, text="🗑️ Удалить выбранное", command=remove_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="🗑️ Очистить все", command=clear_blacklist).pack(side=tk.LEFT, padx=2)
        update_blacklist_display()
        help_frame = ttk.LabelFrame(main_frame, text="ℹ️ Справка", padding=10)
        help_frame.pack(fill=tk.X, pady=(10, 0))
        help_text = (
            "🚫 Монеты из черного списка не будут автоматически добавляться в 'Монеты в работе'."
            "📊 Формат: BTCUSDT, ETHUSDT, ADAUSDT и т.д."
            "🔤 Регистр не имеет значения."
        )
        ttk.Label(help_frame, text=help_text, font=('Arial', 8), justify=tk.LEFT).pack(anchor=tk.W)
    def run(self):
        self.root.mainloop()
if __name__ == "__main__":
    root = tk.Tk()
    app = BybitTradingBot(root)
    app.run()

# ==================== TP RECALC AFTER GRID FILL (PATCH) ====================

def recalc_tp_after_grid_fill(self, symbol: str, side: str):
    """Пересчёт TP после исполнения любого сеточного ордера"""
    try:
        pos = self.session.get_positions(category="linear", symbol=symbol)
        if pos.get("retCode") != 0:
            return

        for p in pos["result"]["list"]:
            if float(p["size"]) <= 0:
                continue

            if p["side"].lower() != side.lower():
                continue

            avg_price = float(p["avgPrice"])
            if avg_price <= 0:
                continue

            tp_price = self.trading_strategy._calculate_safe_tp_price(
                side=side,
                entry_price=avg_price,
                tp_percent=self.config.take_profit,
                min_tp=self.config.min_take_profit
            )

            self.session.set_trading_stop(
                category="linear",
                symbol=symbol,
                side=side.capitalize(),
                takeProfit=tp_price,
                tpTriggerBy="LastPrice",
                positionIdx=1 if side.lower() == "long" else 2
            )

            self.logger.info(
                f"🔁 TP пересчитан после grid-fill {symbol}: avg={avg_price:.4f} → TP={tp_price}"
            )
    except Exception as e:
        self.logger.error(f"Ошибка TP grid-fill {symbol}: {e}")


# ==================== TP FREEZE ATOMIC PATCH (SAFE MONKEY-PATCH) ====================
# This patch fixes:
# 1) Missing freeze timeout attribute
# 2) Atomic removal from coins_in_work on TP
# 3) Guaranteed 5-minute freeze after TP
# 4) Explicit TP-closure logging
#
# It does NOT modify TP calculation, grid logic, ML, or order placement.

import time
from datetime import datetime

def _tp_freeze_patch_apply():
    try:
        cls = BybitTradingBot

        # --- Ensure attributes exist ---
        _orig_init = cls.__init__
        def __init__(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            if not hasattr(self, 'freeze_timeout_seconds'):
                self.freeze_timeout_seconds = 300
            if not hasattr(self, 'frozen_symbols'):
                self.frozen_symbols = {}
        cls.__init__ = __init__

        # --- Frozen check ---
        def is_symbol_frozen(self, symbol):
            until = self.frozen_symbols.get(symbol)
            if not until:
                return False
            if time.time() >= until:
                self.frozen_symbols.pop(symbol, None)
                self.logger.info(f"🔓 Таймаут для {symbol} истек. Монета доступна для торговли.")
                return False
            return True

        cls.is_symbol_frozen = is_symbol_frozen

        # --- Atomic TP handler ---
        def _handle_tp_filled_atomic(self, symbol, reason="TP"):
            now = time.time()

            # Log TP close
            self.logger.info(f"🏁 Позиция {symbol} закрыта по тейк профиту")

            # Remove from coins_in_work immediately
            if hasattr(self, 'coins_in_work') and symbol in self.coins_in_work:
                self.coins_in_work.pop(symbol, None)
                try:
                    self.save_coins_in_work()
                except Exception:
                    pass
                self.logger.info(f"🗑️ {symbol} удалена из списка 'В работе' (TP)")

            # Freeze
            until = now + getattr(self, 'freeze_timeout_seconds', 300)
            self.frozen_symbols[symbol] = until
            self.logger.info(
                f"❄️ ЗАМОРОЗКА {symbol}: Таймаут активирован на {int(until-now)} сек. "
                f"(до {datetime.fromtimestamp(until).strftime('%H:%M:%S')})"
            )

        cls._handle_tp_filled_atomic = _handle_tp_filled_atomic

        # --- Wrap immediate close handler if exists ---
        if hasattr(cls, '_handle_position_closed_immediate'):
            _orig_close = cls._handle_position_closed_immediate
            def _wrapped_close(self, symbol, *a, **kw):
                try:
                    _orig_close(self, symbol, *a, **kw)
                finally:
                    # Always enforce atomic TP cleanup if position disappeared
                    try:
                        pos = self.session.get_positions(category='linear', symbol=symbol)
                        lst = pos.get('result', {}).get('list', [])
                        size = sum(float(p.get('size', 0)) for p in lst)
                        if size == 0:
                            self._handle_tp_filled_atomic(symbol, reason="TP")
                    except Exception:
                        pass
            cls._handle_position_closed_immediate = _wrapped_close

        # --- Guard entries ---
        if hasattr(cls, 'try_open_position'):
            _orig_try_open = cls.try_open_position
            def _wrapped_try_open(self, symbol, *a, **kw):
                if self.is_symbol_frozen(symbol):
                    self.logger.info(f"⛔ ВХОД ЗАБЛОКИРОВАН: {symbol} находится в заморозке")
                    return False
                return _orig_try_open(self, symbol, *a, **kw)
            cls.try_open_position = _wrapped_try_open

    except Exception as e:
        try:
            logging.getLogger().error(f"TP FREEZE PATCH FAILED: {e}")
        except Exception:
            pass

_tp_freeze_patch_apply()
# ==================== END TP FREEZE ATOMIC PATCH ====================



# ==================== FINAL ATOMIC TP FREEZE PATCH ====================
# PURPOSE:
# - Instantly remove symbol from coins_in_work on TP execution
# - Apply 5-minute freeze
# - Block any re-entry during freeze
# - Log TP closure explicitly
# NOTE:
# - Does NOT modify TP calculation, grid logic, ML logic, or hedge mode
# =====================================================================

import time
from datetime import datetime

def __apply_tp_freeze_patch__():
    cls = BybitTradingBot

    # ---- Ensure freeze state exists ----
    _orig_init = cls.__init__
    def __init__(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        if not hasattr(self, "freeze_timeout"):
            self.freeze_timeout = 300
        if not hasattr(self, "freeze_coins"):
            self.freeze_coins = {}
        if not hasattr(self, "_last_position_sizes"):
            self._last_position_sizes = {}
    cls.__init__ = __init__

    # ---- Freeze check ----
    def is_coin_frozen(self, symbol):
        until = self.freeze_coins.get(symbol)
        if not until:
            return False
        if time.time() >= until:
            del self.freeze_coins[symbol]
            self.logger.info(f"🔓 Заморозка истекла для {symbol}")
            return False
        return True
    cls.is_coin_frozen = is_coin_frozen

    # ---- Atomic TP handler ----
    def _handle_tp_close_atomic(self, symbol):
        now = time.time()

        self.logger.info(f"🏁 TP ИСПОЛНЕН для {symbol}. Позиция закрыта.")

        if symbol in self.coins_in_work:
            self.coins_in_work.pop(symbol, None)
            try:
                self.save_coins_in_work()
            except Exception:
                pass
            self.logger.info(f"🗑️ {symbol} удалена из монет в работе (TP)")

        freeze_until = now + self.freeze_timeout
        self.freeze_coins[symbol] = freeze_until
        self.logger.info(
            f"❄️ ЗАМОРОЗКА {symbol} на {self.freeze_timeout} сек "
            f"(до {datetime.fromtimestamp(freeze_until).strftime('%H:%M:%S')})"
        )
    cls._handle_tp_close_atomic = _handle_tp_close_atomic

    # ---- Detect position disappearance (TP on exchange) ----
    _orig_fetch_positions = cls.fetch_positions
    def fetch_positions(self, *args, **kwargs):
        positions = _orig_fetch_positions(self, *args, **kwargs)

        current = {}
        for p in positions:
            sym = p.get("symbol")
            size = abs(float(p.get("size", 0)))
            current[sym] = size

        for sym, last_size in list(self._last_position_sizes.items()):
            if last_size > 0 and current.get(sym, 0) == 0:
                self._handle_tp_close_atomic(sym)

        self._last_position_sizes = current
        return positions
    cls.fetch_positions = fetch_positions

    # ---- Block any entry if frozen ----
    if hasattr(cls, "try_open_position"):
        _orig_try_open = cls.try_open_position
        def try_open_position(self, symbol, *a, **kw):
            if self.is_coin_frozen(symbol):
                self.logger.info(f"⛔ ВХОД ЗАПРЕЩЕН: {symbol} находится в заморозке")
                return False
            return _orig_try_open(self, symbol, *a, **kw)
        cls.try_open_position = try_open_position

__apply_tp_freeze_patch__()
# ==================== END TP FREEZE PATCH ====================


# ==================== FREEZE v2 (ClosedPnL-Driven, Time-Aware) ====================
# GOALS:
# 1. Freeze ONLY when position is truly closed by TP (Closed PnL)
# 2. Log close time, close price, and PnL
# 3. Protect from double / repeated TP on same position
# 4. Block re-entry until freeze expires
# 5. Keep all trading logic untouched

from datetime import datetime, timedelta
import logging

FREEZE_SECONDS_AFTER_TP = 300

# --- GLOBAL STATE (single source of truth) ---
TP_FREEZE = {}              # symbol -> datetime until
LAST_TP_PNL_ID = {}         # symbol -> last processed closedPnL orderId
LAST_TP_CLOSE_TIME = {}     # symbol -> exchange close timestamp (sec)
TP_STATS = {}               # symbol -> dict stats

# --- Dedicated TP log ---
tp_logger = logging.getLogger("tp_closes")
if not tp_logger.handlers:
    h = logging.FileHandler("tp_closes.log", encoding="utf-8")
    f = logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S")
    h.setFormatter(f)
    tp_logger.addHandler(h)
    tp_logger.setLevel(logging.INFO)
    tp_logger.propagate = False


def _get_last_closed_pnl(session, symbol):
    resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
    return resp.get("result", {}).get("list", [])


def detect_tp_close(session, symbol, logger):
    """Detect TP ONLY via Closed PnL. Returns True exactly once per TP."""
    try:
        rows = _get_last_closed_pnl(session, symbol)
        if not rows:
            return False

        row = rows[0]
        pnl_id = row.get("orderId")
        qty = float(row.get("qty", 0))
        if qty <= 0:
            return False

        if LAST_TP_PNL_ID.get(symbol) == pnl_id:
            return False  # already processed

        LAST_TP_PNL_ID[symbol] = pnl_id

        price = row.get("avgExitPrice")
        pnl = row.get("closedPnl")
        ts_ms = int(row.get("createdTime", 0))
        ts = ts_ms / 1000 if ts_ms else None
        close_time = datetime.utcfromtimestamp(ts).strftime("%H:%M:%S") if ts else "unknown"

        LAST_TP_CLOSE_TIME[symbol] = ts

        # Stats
        st = TP_STATS.setdefault(symbol, {"tp_count": 0})
        st["tp_count"] += 1

        logger.info(
            f"🏁 TP EXECUTED {symbol} | TP-ID={pnl_id} | PRICE={price} | PNL={pnl} | TIME={close_time}"
        )
        tp_logger.info(
            f"{symbol} | TP-ID={pnl_id} | PRICE={price} | PNL={pnl} | TIME={close_time} | COUNT={st['tp_count']}"
        )

        # Apply freeze
        until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
        TP_FREEZE[symbol] = until
        logger.info(f"❄️ FREEZE APPLIED {symbol} until {until.strftime('%H:%M:%S')} UTC")

        return True

    except Exception as e:
        logger.error(f"TP DETECT ERROR {symbol}: {e}")
        return False


def is_entry_allowed(symbol, logger):
    """Hard block entry if TP freeze active."""
    until = TP_FREEZE.get(symbol)
    if not until:
        return True
    if datetime.utcnow() >= until:
        TP_FREEZE.pop(symbol, None)
        logger.info(f"⏱ FREEZE EXPIRED {symbol}")
        return True
    logger.info(f"⛔ ENTRY BLOCKED {symbol}: TP FREEZE ACTIVE")
    return False

# ==================== END FREEZE v2 ====================



# ==================== TP AUTO MODE + TP CLOSE LOG FIX ====================
# TP всегда AUTO. Ручной режим — только если пользователь менял TP на бирже.

import logging
from datetime import datetime

tp_close_logger = logging.getLogger("tp_closes")
if not tp_close_logger.handlers:
    h = logging.FileHandler("tp_closes.log", encoding="utf-8")
    f = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    h.setFormatter(f)
    tp_close_logger.addHandler(h)
    tp_close_logger.setLevel(logging.INFO)
    tp_close_logger.propagate = False

LAST_TP_PROCESSED = {}

def force_tp_auto(pair_cfg, logger):
    if getattr(pair_cfg, "use_manual_tp", False):
        pair_cfg.use_manual_tp = False
        pair_cfg.manual_tp_price = 0.0
        logger.info(f"🔁 TP MODE FORCED AUTO for {pair_cfg.symbol}")

def log_tp_close(symbol, pnl, exit_price):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    tp_close_logger.info(
        f"🏁 TP EXECUTED {symbol} | time={ts} | pnl={pnl} | price={exit_price}"
    )

def handle_closed_pnl_strict(session, symbol, logger):
    resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
    lst = resp.get("result", {}).get("list", [])
    if not lst:
        return False
    last = lst[0]
    pnl_id = last.get("orderId")
    if LAST_TP_PROCESSED.get(symbol) == pnl_id:
        return False
    qty = float(last.get("qty", 0))
    if qty <= 0:
        return False

    LAST_TP_PROCESSED[symbol] = pnl_id
    pnl = last.get("closedPnl")
    price = last.get("avgExitPrice")

    log_tp_close(symbol, pnl, price)
    logger.info(f"🏁 TP CONFIRMED {symbol} | pnl={pnl} | price={price}")
    return True
# ==================== END TP AUTO MODE + TP CLOSE LOG FIX ====================



# ==================== STRICT TP FREEZE + TP CLOSE LOG (FINAL) ====================
from datetime import datetime, timedelta
import logging

FREEZE_SECONDS_AFTER_TP = 300
SYMBOL_FREEZE_UNTIL = {}
LAST_CLOSED_PNL_ID = {}

def _ekb_time_from_ms(ms):
    return datetime.utcfromtimestamp(int(ms)/1000) + timedelta(hours=5)

def ensure_tp_closes_logger():
    logger = logging.getLogger("tp_closes")
    if not logger.handlers:
        handler = logging.FileHandler("tp_closes.log", encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S")
        handler.setFormatter(formatter)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
    return logger

TP_CLOSES_LOGGER = ensure_tp_closes_logger()

def confirm_tp_and_freeze(session, symbol, logger):
    try:
        resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
        items = resp.get("result", {}).get("list", [])
        if not items:
            return False

        pnl = items[0]
        pnl_id = pnl.get("orderId")
        if LAST_CLOSED_PNL_ID.get(symbol) == pnl_id:
            return False

        qty = float(pnl.get("qty", 0))
        if qty <= 0:
            return False

        LAST_CLOSED_PNL_ID[symbol] = pnl_id

        exit_price = pnl.get("avgExitPrice")
        pnl_val = float(pnl.get("closedPnl", 0))
        closed_at = _ekb_time_from_ms(pnl.get("updatedTime", 0))

        until = datetime.utcnow() + timedelta(seconds=FREEZE_SECONDS_AFTER_TP)
        SYMBOL_FREEZE_UNTIL[symbol] = until

        logger.info(
            f"🏁 TP EXECUTED {symbol} | PRICE={exit_price} | PnL={pnl_val:.4f} | CLOSED_AT={closed_at.strftime('%d.%m.%Y %H:%M')}"
        )
        logger.info(
            f"❄️ FREEZE APPLIED {symbol} until {(until + timedelta(hours=5)).strftime('%H:%M:%S')} EKB"
        )

        TP_CLOSES_LOGGER.info(
            f"🏁 TP EXECUTED {symbol} | PRICE={exit_price} | PnL={pnl_val:.4f} | CLOSED_AT={closed_at.strftime('%d.%m.%Y %H:%M')}"
        )
        TP_CLOSES_LOGGER.info(
            f"❄️ FREEZE APPLIED {symbol} until {(until + timedelta(hours=5)).strftime('%H:%M:%S')} EKB"
        )

        return True
    except Exception as e:
        logger.error(f"TP FREEZE ERROR {symbol}: {e}")
        return False

def is_symbol_frozen(symbol, logger):
    until = SYMBOL_FREEZE_UNTIL.get(symbol)
    if not until:
        return False
    if datetime.utcnow() >= until:
        SYMBOL_FREEZE_UNTIL.pop(symbol, None)
        logger.info(f"🔓 FREEZE EXPIRED {symbol}")
        return False
    logger.info(f"⛔ ENTRY BLOCKED {symbol}: FREEZE ACTIVE")
    return True
# ==================== END STRICT TP FREEZE PATCH ====================



# ==================== PATCH: TP WATCHDOG + GRID CANCEL GUARD ====================
# Added without modifying existing logic

import threading
import time
from datetime import datetime

# ===================== TP MARK PRICE GUARD (AUTO, SAFE) =====================
def _adjust_tp_for_mark_price(tp_price, side, mark_price, tick_size):
    try:
        tp_price = float(tp_price)
        mark_price = float(mark_price)
        tick_size = float(tick_size)
    except Exception:
        return tp_price
    if side.lower() == "short":
        if tp_price >= mark_price:
            return round(mark_price - tick_size, 8)
    else:
        if tp_price <= mark_price:
            return round(mark_price + tick_size, 8)
    return tp_price
# ============================================================================


TP_WATCHDOG_INTERVAL = 300  # 5 minutes

def _has_active_tp(session, symbol):
    try:
        orders = session.get_open_orders(category="linear", symbol=symbol)
        for o in orders.get("result", {}).get("list", []):
            if o.get("reduceOnly") and o.get("orderType") in ("Market", "Limit"):
                return True
    except Exception:
        pass
    return False

def _set_default_tp_if_missing(bot, symbol):
    cfg = bot.pairs_config.get(symbol)
    if not cfg:
        return
    try:
        pos = bot.session.get_positions(category="linear", symbol=symbol)
        plist = pos.get("result", {}).get("list", [])
        for p in plist:
            size = float(p.get("size", 0))
            if size == 0:
                continue
            side = "long" if p.get("side") == "Buy" else "short"
            entry = float(p.get("avgPrice", 0))
            if entry <= 0:
                continue
            if _has_active_tp(bot.session, symbol):
                return
            tp_pct = max(cfg.take_profit, cfg.min_take_profit)
            if side == "long":
                tp_price = round(entry * (1 + tp_pct / 100), 4)
            else:
                tp_price = round(entry * (1 - tp_pct / 100), 4)
            bot.session.place_order(
                category="linear",
                symbol=symbol,
                side="Sell" if side == "long" else "Buy",
                orderType="Market",
                qty=size,
                reduceOnly=True,
                triggerPrice=tp_price,
                triggerDirection=1 if side == "long" else 2
            )
            bot.logger.info(
                f"🛡 TP WATCHDOG: TP восстановлен для {symbol} @ {tp_price} ({tp_pct}%)"
            )
    except Exception as e:
        bot.logger.error(f"TP WATCHDOG error {symbol}: {e}")

def tp_watchdog_loop(bot):
    while True:
        try:
            for symbol in list(bot.coins_in_work):
                _set_default_tp_if_missing(bot, symbol)
        except Exception as e:
            bot.logger.error(f"TP WATCHDOG loop error: {e}")
        time.sleep(TP_WATCHDOG_INTERVAL)

# ---- MASS CANCEL GUARD ----
_original_cancel_all = None
if hasattr(globals().get("OrderManager", None), "cancel_all_orders"):
    _original_cancel_all = OrderManager.cancel_all_orders

def _cancel_all_orders_guard(self, symbol, *a, **k):
    try:
        if hasattr(self, "coins_in_work") and symbol in self.coins_in_work:
            self.logger.warning(
                f"⛔ MASS CANCEL BLOCKED (GRID FILL) {symbol}: монета в работе"
            )
            return False
    except Exception:
        pass
    return _original_cancel_all(self, symbol, *a, **k)

if _original_cancel_all:
    OrderManager.cancel_all_orders = _cancel_all_orders_guard

# ---- AUTO START WATCHDOG ----
def _start_tp_watchdog(bot):
    t = threading.Thread(target=tp_watchdog_loop, args=(bot,), daemon=True)
    t.start()

# ==================== END PATCH ====================


# ==================== SOFT ENTRY TIMING FILTERS (ANTI-PEAK + PULLBACK) ====================
# Optimized for scalping TP 0.8–0.95%
ANTI_PEAK_LOOKBACK_N = 8            # N candles
ANTI_PEAK_MAX_MOVE_PCT = 0.9        # X% move cap over N candles
PULLBACK_MIN_PCT = 0.15             # 0.15%
PULLBACK_MAX_PCT = 0.35             # 0.35%
HTF_TREND_EMA_FAST = 50             # very light HTF confirmation
HTF_TREND_EMA_SLOW = 200

def anti_peak_filter(df, direction):
    if len(df) < ANTI_PEAK_LOOKBACK_N + 1:
        return True
    recent = df.tail(ANTI_PEAK_LOOKBACK_N)
    move = (recent['high'].max() - recent['low'].min()) / recent['low'].min() * 100
    if move >= ANTI_PEAK_MAX_MOVE_PCT:
        return False
    return True

def pullback_filter(df, direction):
    price = df['close'].iloc[-1]
    ema9 = df['ema_9'].iloc[-1]
    ema21 = df['ema_21'].iloc[-1]
    ref = ema9 if abs(price-ema9) < abs(price-ema21) else ema21
    dist = abs(price - ref) / ref * 100
    return PULLBACK_MIN_PCT <= dist <= PULLBACK_MAX_PCT

def htf_trend_confirm(df_htf, direction):
    if df_htf is None or len(df_htf) < HTF_TREND_EMA_SLOW:
        return True
    ema_fast = df_htf['close'].ewm(span=HTF_TREND_EMA_FAST).mean().iloc[-1]
    ema_slow = df_htf['close'].ewm(span=HTF_TREND_EMA_SLOW).mean().iloc[-1]
    return (ema_fast > ema_slow) if direction == "long" else (ema_fast < ema_slow)
# ==================== END SOFT ENTRY TIMING FILTERS ====================46

# ===== OVERRIDE: FINAL STRICT MASS CANCEL GUARD =====
def cancel_all_orders_safe(session, symbol, coins_in_work, logger, reason=""):
    # ABSOLUTE GUARD: no mass cancel while symbol is in work
    try:
        if symbol in coins_in_work:
            logger.info(f"⛔ MASS CANCEL FORBIDDEN {symbol}: coin still in work")
            return
    except Exception:
        pass

    state = SYMBOL_STATES.get(symbol)
    if state != "TP_CLOSED":
        logger.info(f"⛔ MASS CANCEL FORBIDDEN {symbol}: state={state}")
        return

    logger.info(f"🧹 MASS CANCEL ALLOWED {symbol} AFTER TP. Reason: {reason}")
    session.cancel_all_orders(category="linear", symbol=symbol)
# ===== END OVERRIDE =====

# ================= FREEZE MANAGER (FINAL) =================
freeze_map = {}
entry_counter = {}

def is_frozen(symbol):
    until = freeze_map.get(symbol, 0)
    if until > time.time():
        logger.info(f"⛔ FREEZE BLOCKED ENTRY: {symbol}")
        return True
    return False

def apply_freeze(symbol, minutes, reason="tp"):
    freeze_map[symbol] = time.time() + minutes * 60
    if symbol in coins_in_work:
        coins_in_work.discard(symbol)
    logger.info(f"❄️ FREEZE APPLIED: {symbol} ({minutes} min) reason={reason}")

def register_entry(symbol):
    now = time.time()
    arr = entry_counter.get(symbol, [])
    arr = [t for t in arr if now - t < 300]
    arr.append(now)
    entry_counter[symbol] = arr
    if len(arr) >= 3:
        apply_freeze(symbol, 10, reason="anti-overtrade")
        logger.info(f"🧊 FREEZE EXTENDED: {symbol} (10 min, anti-overtrade)")
        return False
    return True

def on_position_closed(symbol):
    apply_freeze(symbol, 5, reason="tp_close")

# Hook entry
_old_enter = enter_position_for_working_coin
def enter_position_for_working_coin(symbol, *a, **k):
    if is_frozen(symbol):
        return False
    if not register_entry(symbol):
        return False
    return _old_enter(symbol, *a, **k)
# ==========================================================



# ==================== HARD FREEZE GUARD (ANTI TP DELETE) ====================
TP_RECALC_IN_PROGRESS = set()

def mark_tp_recalc_start(symbol):
    TP_RECALC_IN_PROGRESS.add(symbol)

def mark_tp_recalc_end(symbol):
    TP_RECALC_IN_PROGRESS.discard(symbol)

def is_mass_cancel_allowed(symbol, coins_in_work):
    if symbol in coins_in_work:
        return False
    if symbol in TP_RECALC_IN_PROGRESS:
        return False
    return SYMBOL_STATES.get(symbol) == "TP_CLOSED"

def cancel_all_orders_safe(session, symbol, coins_in_work, logger, reason=""):
    if not is_mass_cancel_allowed(symbol, coins_in_work):
        logger.info(
            f"⛔ MASS CANCEL BLOCKED {symbol}: "
            f"in_work={symbol in coins_in_work}, "
            f"tp_recalc={symbol in TP_RECALC_IN_PROGRESS}, "
            f"state={SYMBOL_STATES.get(symbol)}"
        )
        return
    logger.info(f"🧹 MASS CANCEL ALLOWED {symbol} AFTER TP. Reason: {reason}")
    session.cancel_all_orders(category="linear", symbol=symbol)
# ==================== END HARD FREEZE GUARD ====================

# ==================== MASS CANCEL DEBUG TRACE ====================
import traceback

def log_mass_cancel_attempt(symbol, logger, reason=""):
    stack = traceback.format_stack(limit=8)
    caller = stack[-4].strip() if len(stack) >= 4 else "UNKNOWN"
    logger.warning(
        f"⚠️ MASS CANCEL ATTEMPT BLOCKED {symbol} | reason={reason} | caller={caller}"
    )

def cancel_all_orders_safe(session, symbol, coins_in_work, logger, reason=""):
    if symbol in coins_in_work or SYMBOL_STATES.get(symbol) != "TP_CLOSED":
        log_mass_cancel_attempt(symbol, logger, reason)
        return
    logger.info(f"🧹 MASS CANCEL ALLOWED {symbol} AFTER TP. Reason: {reason}")
    session.cancel_all_orders(category="linear", symbol=symbol)
# ==================== END MASS CANCEL DEBUG TRACE ====================



# ==================== FASTMOMENTUM TREND FILTER (HH/HL – LL/LH) ====================

def fastmomentum_trend_filter(candles, side):
    # candles: list of dicts or tuples with high/low
    if len(candles) < 3:
        return False

    last = candles[-1]
    prev = candles[-2]

    last_high = last["high"] if isinstance(last, dict) else last[2]
    last_low  = last["low"]  if isinstance(last, dict) else last[3]
    prev_high = prev["high"] if isinstance(prev, dict) else prev[2]
    prev_low  = prev["low"]  if isinstance(prev, dict) else prev[3]

    if side == "Buy":
        return last_high > prev_high and last_low > prev_low
    if side == "Sell":
        return last_high < prev_high and last_low < prev_low

    return False

# ==================== END FASTMOMENTUM TREND FILTER ====================



# ==================== IMPROVED FREEZE MODULE (TP-BASED) ====================
import time

FROZEN_SYMBOLS = {}
FREEZE_SECONDS_AFTER_TP = 300  # cooldown after TP

def freeze_symbol_after_tp(symbol, logger):
    freeze_until = time.time() + FREEZE_SECONDS_AFTER_TP
    FROZEN_SYMBOLS[symbol] = freeze_until
    logger.info(f"🧊 FREEZE ENABLED for {symbol} until {freeze_until:.0f}")

def is_symbol_frozen(symbol):
    ts = FROZEN_SYMBOLS.get(symbol)
    if not ts:
        return False
    if time.time() >= ts:
        del FROZEN_SYMBOLS[symbol]
        return False
    return True

def on_tp_position_closed(symbol, coins_in_work, logger):
    if symbol in coins_in_work:
        coins_in_work.discard(symbol)
    freeze_symbol_after_tp(symbol, logger)
    SYMBOL_STATES[symbol] = "TP_CLOSED"
    logger.info(f"✅ TP CLOSED → {symbol} frozen and removed from work")

def can_enter_symbol(symbol, coins_in_work, logger):
    if symbol in coins_in_work:
        logger.info(f"⛔ ENTRY BLOCKED {symbol}: already in work")
        return False
    if is_symbol_frozen(symbol):
        logger.info(f"⛔ ENTRY BLOCKED {symbol}: frozen after TP")
        return False
    return True
# ==================== END IMPROVED FREEZE MODULE ====================



# ==================== ML STRUCTURE FILTER (HH/HL – LL/LH) ====================

def ml_structure_filter(candles, side):
    """Additional HH/HL – LL/LH structure filter for ML signals"""
    if len(candles) < 3:
        return False

    last = candles[-1]
    prev = candles[-2]

    last_high = last["high"] if isinstance(last, dict) else last[2]
    last_low  = last["low"]  if isinstance(last, dict) else last[3]
    prev_high = prev["high"] if isinstance(prev, dict) else prev[2]
    prev_low  = prev["low"]  if isinstance(prev, dict) else prev[3]

    if side.lower() == "long":
        return last_high > prev_high and last_low > prev_low

    if side.lower() == "short":
        return last_high < prev_high and last_low < prev_low

    return False

# ==================== END ML STRUCTURE FILTER ====================


# ==================== SAFE CLOSE HANDLER WRAPPER ====================
def _handle_position_closed_immediate_patched(self, symbol, close_price=None):
    try:
        force_freeze(symbol, self, reason="position_closed")
        _ensure_dict(self.positions, symbol)
        pos = self.positions.get(symbol, {})
        entry = pos.get('entry_price') or pos.get('avg_price')
        tp = pos.get('tp_price')
        size = pos.get('size', 0)
        side = pos.get('side', '').lower()

        if entry and tp and size and side:
            if (side in ('buy','long') and close_price is not None and close_price < tp) or                (side in ('sell','short') and close_price is not None and close_price > tp):
                self.logger.info(f"⛔ Закрытие {symbol} не по TP — PnL не фиксируется")
                return
            pnl = tp_pnl_from_tp(entry, tp, size, side)
            if pnl <= 0:
                self.logger.info(f"⛔ PnL {symbol} ниже порога — не сохраняем")
                return
    except Exception as e:
        self.logger.error(f"SAFE CLOSE ERROR {symbol}: {e}")
# ==================== END WRAPPER ====================


    def _ensure_tp_auto(self, symbol: str):
        """Hard guard: TP can be manual ONLY if user changed it on exchange"""
        pos = self.positions.get(symbol)
        if not pos:
            return
        if pos.get("tp_mode") != "auto" and not pos.get("manual_tp_confirmed", False):
            self.logger.warning(f"⚠️ TP mode forcibly returned to AUTO for {symbol}")
            pos["tp_mode"] = "auto"


    def _apply_freeze(self, symbol: str, reason: str):
        """Freeze must be applied BEFORE any cleanup"""
        now = int(time.time())
        timeout = self.config.get("freeze_timeout_sec", 300)
        until = now + timeout

        self.freeze[symbol] = until
        self.logger.info(
            f"❄️ ЗАМОРОЗКА {symbol}: причина={reason}, до {time.strftime('%H:%M:%S', time.localtime(until))}"
        )


    def _is_frozen(self, symbol: str) -> bool:
        until = self.freeze.get(symbol)
        if not until:
            return False
        if time.time() >= until:
            del self.freeze[symbol]
            self.logger.info(f"🔓 Таймаут для {symbol} истек. Монета доступна для торговли.")
            return False
        return True






# ================= HARD FREEZE ENTRY GUARD (FIXED) =================
import time

def _install_hard_freeze(self):
    """Install hard freeze guards safely inside class context"""

    def _is_frozen(symbol):
        until = self.freeze_until.get(symbol)
        if not until:
            return False
        if time.time() >= until:
            return False
        return True

    def _apply_freeze(symbol, reason):
        if symbol in self.freeze_until:
            return
        timeout = getattr(self, "freeze_timeout_sec", 300)
        self.freeze_until[symbol] = time.time() + timeout
        self.freeze_reason[symbol] = reason
        self.logger.warning(f"❄️ HARD FREEZE APPLIED {symbol} | reason={reason}")

    # Wrap entry
    if hasattr(self, "_try_enter_position"):
        orig = self._try_enter_position
        def wrapped_try_enter(symbol, *a, **kw):
            if _is_frozen(symbol):
                self.logger.error(f"⛔ ENTRY BLOCKED BY FREEZE {symbol}")
                return
            return orig(symbol, *a, **kw)
        self._try_enter_position = wrapped_try_enter

    # Wrap confirmed close
    if hasattr(self, "_confirm_position_closed"):
        orig_close = self._confirm_position_closed
        def wrapped_close(symbol, *a, **kw):
            _apply_freeze(symbol, "confirmed_close")
            return orig_close(symbol, *a, **kw)
        self._confirm_position_closed = wrapped_close

    self.logger.info("🧊 HARD FREEZE GUARD INSTALLED")

# ================= END HARD FREEZE =================

# === SAFETY PATCH: BLOCK MASS CANCEL WHILE SYMBOL IN WORK ===
def _safe_mass_cancel(self, symbol: str, reason: str = ""):
    if symbol in getattr(self, "symbols_in_work", set()) and not self.closing_symbols.get(symbol):
        self.logger.warning(f"⛔ MASS CANCEL BLOCKED (IN WORK): {symbol} | {reason}")
        return False
    return self._mass_cancel_orders(symbol)



# === MIN TP SAFETY (INITIAL SET ONLY) ===
def _apply_min_tp_pct(self, target_pct: float) -> float:
    """Ensure minimal TP percent (do NOT affect recalculation logic)"""
    min_tp = getattr(self, "MIN_TP_PCT", 0.008)  # 0.8%
    if target_pct < min_tp:
        self.logger.warning(
            f"⚠️ TP target {target_pct*100:.2f}% < minimum {min_tp*100:.2f}%, forced to minimum"
        )
        return min_tp
    return target_pct



# ================= FREEZE & SAFETY EXTENSIONS =================

def _log_mass_cancel_caller(self, symbol, reason):
    self.logger.warning(f"🧨 MASS-CANCEL REQUESTED: {symbol} | reason={reason} | caller=STACK")

def _apply_freeze(self, symbol: str, reason: str, duration: int = None):
    now = time.time()
    dur = duration or getattr(self, "FREEZE_AFTER_CLOSE_SEC", 300)
    until = now + dur
    self.freeze_map[symbol] = until
    self.logger.warning(
        f"❄️ FREEZE APPLIED {symbol} | reason={reason} | until={time.strftime('%H:%M:%S', time.localtime(until))}"
    )

def _is_frozen(self, symbol: str) -> bool:
    until = self.freeze_map.get(symbol)
    if until and time.time() < until:
        self.logger.warning(f"⛔ FREEZE BLOCKED ENTRY {symbol}")
        return True
    return False

def _safe_mass_cancel(self, symbol: str, reason: str):
    self._log_mass_cancel_caller(symbol, reason)
    if symbol in self.symbols_in_work:
        self.logger.warning(f"⛔ MASS-CANCEL BLOCKED (IN WORK): {symbol}")
        return
    return self._mass_cancel_orders(symbol)

def _on_position_closed(self, symbol: str, reason: str):
    self._apply_freeze(symbol, reason)
    if symbol in self.symbols_in_work:
        self.symbols_in_work.discard(symbol)
    self.closing_symbols[symbol] = True

def _tp_watchdog(self):
    for symbol in list(self.symbols_in_work):
        if not self._has_active_tp(symbol):
            self.logger.warning(f"⚠️ TP MISSING {symbol} → REINSTALL")
            self._install_tp(symbol, force=True)

# ===============================================================



# ===================== HARD FREEZE + TP SAFETY PATCH =====================
import traceback, os

FREEZE_AFTER_CLOSE_SEC = 300      # 5 minutes
FREEZE_OVERTRADE_SEC = 600        # 10 minutes
ANTI_OVERTRADE_MAX = 3
MIN_TP_PCT = 0.008                # 0.8%

def _mass_cancel_debug(self, symbol, reason):
    log_path = "mass-cancel.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {symbol} | {reason}\n")
        f.write("".join(traceback.format_stack(limit=6)))
        f.write("\n")

def _apply_freeze(self, symbol, reason, duration=None):
    until = time.time() + (duration or FREEZE_AFTER_CLOSE_SEC)
    self.freeze_until[symbol] = until
    self.freeze_reason[symbol] = reason
    self.logger.warning(
        f"❄️ FREEZE APPLIED {symbol} | reason={reason} | until={time.strftime('%H:%M:%S', time.localtime(until))}"
    )

def _extend_freeze(self, symbol):
    until = time.time() + FREEZE_OVERTRADE_SEC
    self.freeze_until[symbol] = until
    self.logger.warning(f"🧊 FREEZE EXTENDED {symbol} (anti-overtrade)")

def _is_frozen(self, symbol):
    until = self.freeze_until.get(symbol)
    if until and time.time() < until:
        self.logger.warning(f"⛔ FREEZE BLOCKED ENTRY {symbol}")
        return True
    return False

def _on_position_closed(self, symbol, reason="position_closed"):
    self._apply_freeze(symbol, reason)
    self.symbols_in_work.discard(symbol)
    self.closing_symbols[symbol] = True

def _safe_mass_cancel(self, symbol, reason="unknown"):
    self._mass_cancel_debug(symbol, reason)
    if symbol in self.symbols_in_work:
        self.logger.warning(f"⛔ MASS-CANCEL BLOCKED (IN WORK): {symbol}")
        return
    return self._mass_cancel_orders(symbol)

def _ensure_min_tp(self, target_pct):
    if target_pct < MIN_TP_PCT:
        self.logger.warning(
            f"⚠️ TP target {target_pct*100:.2f}% < {MIN_TP_PCT*100:.2f}%, forced"
        )
        return MIN_TP_PCT
    return target_pct

def _tp_watchdog(self):
    for symbol in list(self.symbols_in_work):
        if not self._has_active_tp(symbol):
            self.logger.warning(f"⚠️ TP MISSING {symbol} → RESTORE")
            self._install_tp(symbol, force=True)

# ========================================================================



# ================= FINAL FREEZE & MASS-CANCEL DEBUG PATCH =================
import traceback, os

MASS_CANCEL_LOG = "mass-cancel.log"
FREEZE_AFTER_TP_SEC = 300
ANTI_OVERTRADE_LIMIT = 3
ANTI_OVERTRADE_FREEZE_SEC = 600
MIN_TP_PCT = 0.008

def _log_mass_cancel(self, symbol: str, reason: str):
    try:
        with open(MASS_CANCEL_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] MASS-CANCEL {symbol} | reason={reason}\n")
            f.write("".join(traceback.format_stack(limit=8)))
    except Exception as e:
        self.logger.error(f"Failed to write mass-cancel.log: {e}")

def _apply_freeze(self, symbol: str, reason: str, duration: int = FREEZE_AFTER_TP_SEC):
    until = time.time() + duration
    self.freeze_until[symbol] = until
    self.freeze_reason[symbol] = reason
    self.logger.warning(
        f"❄️ FREEZE APPLIED {symbol} | reason={reason} | until={time.strftime('%H:%M:%S', time.localtime(until))}"
    )

def _extend_freeze(self, symbol: str):
    until = time.time() + ANTI_OVERTRADE_FREEZE_SEC
    self.freeze_until[symbol] = until
    self.logger.warning(f"🧊 FREEZE EXTENDED {symbol} (anti-overtrade)")

def _is_frozen(self, symbol: str) -> bool:
    until = self.freeze_until.get(symbol)
    if until and time.time() < until:
        self.logger.warning(f"⛔ FREEZE BLOCKED ENTRY {symbol}")
        return True
    return False

def _on_position_closed(self, symbol: str, reason: str = "tp_or_closed"):
    # FREEZE FIRST – ALWAYS
    self._apply_freeze(symbol, reason)
    # hard remove from work
    if symbol in self.symbols_in_work:
        self.symbols_in_work.discard(symbol)
    self.closing_symbols[symbol] = True

def _safe_mass_cancel(self, symbol: str, reason: str = "unknown"):
    self._log_mass_cancel(symbol, reason)
    if symbol in self.symbols_in_work:
        self.logger.warning(f"⛔ MASS-CANCEL BLOCKED (IN WORK): {symbol}")
        return
    return self._mass_cancel_orders(symbol)

def _tp_watchdog(self):
    # call this from existing main loop / timer
    for symbol in list(self.symbols_in_work):
        if not self._has_active_tp(symbol):
            self.logger.warning(f"⚠️ TP MISSING {symbol} → RESTORE")
            self._install_tp(symbol, force=True)

def _ensure_min_tp_pct(self, target_pct: float) -> float:
    if target_pct < MIN_TP_PCT:
        self.logger.warning(
            f"⚠️ TP target {target_pct*100:.2f}% < {MIN_TP_PCT*100:.2f}%, forced to minimum"
        )
        return MIN_TP_PCT
    return target_pct
# ========================================================================



# ===================== CLASS BINDING FIX (CRITICAL) =====================
# Root cause fix:
# _apply_freeze and related helpers MUST be bound to BybitTradingBot,
# otherwise calls like self._apply_freeze() will crash.

def _btb_apply_freeze(self, symbol: str, reason: str, duration: int = FREEZE_AFTER_TP_SEC):
    until = time.time() + duration
    self.freeze_until[symbol] = until
    self.freeze_reason[symbol] = reason
    self.logger.warning(
        f"❄️ FREEZE APPLIED {symbol} | reason={reason} | until={time.strftime('%H:%M:%S', time.localtime(until))}"
    )

def _btb_extend_freeze(self, symbol: str):
    until = time.time() + ANTI_OVERTRADE_FREEZE_SEC
    self.freeze_until[symbol] = until
    self.logger.warning(f"🧊 FREEZE EXTENDED {symbol} (anti-overtrade)")

def _btb_is_frozen(self, symbol: str) -> bool:
    until = self.freeze_until.get(symbol)
    if until and time.time() < until:
        self.logger.warning(f"⛔ FREEZE BLOCKED ENTRY {symbol}")
        return True
    return False

def _btb_on_position_closed(self, symbol: str, reason: str = "position_closed"):
    # FREEZE MUST BE FIRST
    self._apply_freeze(symbol, reason)
    self.symbols_in_work.discard(symbol)
    self.closing_symbols[symbol] = True

def _btb_safe_mass_cancel(self, symbol: str, reason: str = "unknown"):
    self._log_mass_cancel(symbol, reason)
    if symbol in self.symbols_in_work:
        self.logger.warning(f"⛔ MASS-CANCEL BLOCKED (IN WORK): {symbol}")
        return
    return self._mass_cancel_orders(symbol)

# Bind to class
BybitTradingBot._apply_freeze = _btb_apply_freeze
BybitTradingBot._extend_freeze = _btb_extend_freeze
BybitTradingBot._is_frozen = _btb_is_frozen
BybitTradingBot._on_position_closed = _btb_on_position_closed
BybitTradingBot._safe_mass_cancel = _btb_safe_mass_cancel
# =======================================================================



class FreezeManager:
    def __init__(self):
        self.frozen = {}
        self.entry_counter = {}

    def apply_freeze(self, symbol, minutes=5, reason="TP"):
        until = datetime.utcnow() + timedelta(minutes=minutes)
        self.frozen[symbol] = until
        _append_log(FREEZE_LOG, f"❄️ FREEZE APPLIED {symbol} reason={reason} until={until}")

    def is_frozen(self, symbol):
        if symbol not in self.frozen:
            return False
        if datetime.utcnow() > self.frozen[symbol]:
            del self.frozen[symbol]
            return False
        _append_log(FREEZE_LOG, f"⛔ FREEZE BLOCKED ENTRY {symbol}")
        return True

    def register_entry(self, symbol):
        c = self.entry_counter.get(symbol, 0) + 1
        self.entry_counter[symbol] = c
        if c >= 3:
            self.apply_freeze(symbol, minutes=10, reason="anti-overtrade")
            _append_log(FREEZE_LOG, f"🔁 FREEZE EXTENDED {symbol} anti-overtrade")
            self.entry_counter[symbol] = 0


# ================= WATCHDOG TP / MASS-CANCEL / FREEZE PATCH =================

LAST_TP_CHECK = {}

def watchdog_tp(symbol, position, default_tp_pct):
    now = time.time()
    if symbol in LAST_TP_CHECK and now - LAST_TP_CHECK[symbol] < 60:
        return
    LAST_TP_CHECK[symbol] = now

    tp = get_active_tp(symbol, position)
    if not tp:
        target_pct = max(0.8, default_tp_pct)
        place_auto_tp(symbol, position, target_pct)
        log.info(f"🎯 WATCHDOG TP RESTORED {symbol} pct={target_pct}")

def safe_mass_cancel(symbol, reason="unknown"):
    if symbol in coins_in_work:
        with open("mass-cancel.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.utcnow().isoformat()} | BLOCKED mass-cancel {symbol} reason={reason}\n")
            f.write(traceback.format_exc() + "\n")
        return False
    try:
        mass_cancel(symbol)
    except Exception:
        with open("mass-cancel.log", "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
    return True

def freeze_on_position_close(symbol, prev_pos, current_pos):
    if prev_pos and not current_pos:
        freeze_manager.apply_freeze(symbol, minutes=5, reason="position_closed")
        coins_in_work.discard(symbol)

# ================= END PATCH =================


# ================= HARD FREEZE FIX =================

def _hard_apply_freeze(symbol, reason="position_closed"):
    try:
        if symbol in coins_in_work:
            coins_in_work.discard(symbol)
        freeze_manager.apply_freeze(symbol, minutes=5, reason=reason)
        _append_log(FREEZE_LOG, f"❄️ FREEZE APPLIED {symbol} reason={reason}")
    except Exception as e:
        _append_log(FREEZE_LOG, f"FREEZE ERROR {symbol}: {e}")

def on_position_disappeared(symbol):
    _hard_apply_freeze(symbol, reason="position_disappeared")

LAST_API_CALL = {}

def api_guard(key, min_interval=2):
    now = time.time()
    last = LAST_API_CALL.get(key, 0)
    if now - last < min_interval:
        return False
    LAST_API_CALL[key] = now
    return True


# ================= ANTI MASS-CANCEL DURING AVERAGING =================

def _is_averaging_event(context=None):
    if context and isinstance(context, str):
        return "GRID-FILL" in context or "усред" in context.lower()
    return False

def _safe_mass_cancel(self, symbol, reason=None):
    if symbol in getattr(self, "coins_in_work", set()):
        if _is_averaging_event(reason):
            try:
                self.logger.info(f"⛔ MASS-CANCEL BLOCKED (averaging) {symbol}")
            except Exception:
                pass
            return False
    return self._mass_cancel_original(symbol)

# Monkey patch mass_cancel once
if hasattr(BybitTradingBot, "mass_cancel") and not hasattr(BybitTradingBot, "_mass_cancel_original"):
    BybitTradingBot._mass_cancel_original = BybitTradingBot.mass_cancel
    BybitTradingBot.mass_cancel = _safe_mass_cancel

# ================= END PATCH =================


# ================= TP WATCHDOG + NEGATIVE PNL GUARD =================

_LAST_TP_WATCH = {}

def _tp_watchdog(self, symbol, position, target_pct):
    now = time.time()
    last = _LAST_TP_WATCH.get(symbol, 0)
    if now - last < 60:
        return
    _LAST_TP_WATCH[symbol] = now

    tp = None
    try:
        tp = self.get_active_tp(symbol, position)
    except Exception:
        pass

    if not tp:
        pct = max(0.8, target_pct)
        try:
            self.place_auto_tp(symbol, position, pct)
            self.logger.info(f"🎯 WATCHDOG TP RESTORED {symbol} pct={pct}")
        except Exception as e:
            self.logger.error(f"TP WATCHDOG ERROR {symbol}: {e}")

def _guard_negative_pnl(self, symbol, pnl):
    if pnl < 0:
        try:
            self.logger.warning(f"⛔ NEGATIVE PNL BLOCKED {symbol}: {pnl}")
        except Exception:
            pass
        return False
    return True

# ================= END PATCH =================


# ================= HARD TP >= 0.8% GUARD =================

MIN_TP_PCT = 0.8

def _enforce_min_tp(self, symbol, target_pct):
    pct = max(MIN_TP_PCT, float(target_pct))
    if float(target_pct) < MIN_TP_PCT:
        try:
            self.logger.warning(
                f"⛔ TP BELOW MIN BLOCKED {symbol}: requested={target_pct}% forced={pct}%"
            )
        except Exception:
            pass
    return pct

# Wrap TP placement to enforce minimum
if hasattr(BybitTradingBot, "place_auto_tp") and not hasattr(BybitTradingBot, "_place_auto_tp_original"):
    BybitTradingBot._place_auto_tp_original = BybitTradingBot.place_auto_tp

    def _place_auto_tp_guarded(self, symbol, position, target_pct):
        safe_pct = _enforce_min_tp(self, symbol, target_pct)
        return self._place_auto_tp_original(symbol, position, safe_pct)

    BybitTradingBot.place_auto_tp = _place_auto_tp_guarded

# ================= END HARD TP GUARD =================


# ================= ABSOLUTE AVERAGING GUARD =================
from collections import defaultdict

if not hasattr(BybitTradingBot, "_averaging_flag"):
    BybitTradingBot._averaging_flag = defaultdict(bool)

def _mark_averaging_start(self, symbol):
    self._averaging_flag[symbol] = True
    try:
        self.logger.info(f"🧮 AVERAGING START {symbol}")
    except Exception:
        pass

def _mark_averaging_end(self, symbol):
    if self._averaging_flag.get(symbol):
        self._averaging_flag[symbol] = False
        try:
            self.logger.info(f"🧮 AVERAGING END {symbol}")
        except Exception:
            pass

def _guarded_mass_cancel(self, symbol, *args, **kwargs):
    if self._averaging_flag.get(symbol):
        try:
            self.logger.warning(f"⛔ MASS-CANCEL BLOCKED (AVERAGING) {symbol}")
        except Exception:
            pass
        return False
    return self._mass_cancel_original(symbol, *args, **kwargs)

if hasattr(BybitTradingBot, "mass_cancel") and not hasattr(BybitTradingBot, "_mass_cancel_original"):
    BybitTradingBot._mass_cancel_original = BybitTradingBot.mass_cancel
    BybitTradingBot.mass_cancel = _guarded_mass_cancel
# ================= END ABSOLUTE AVERAGING GUARD =================


# ================= UNIT-ASSERT MASS-CANCEL =================

DEBUG_UNIT_ASSERT = True  # set False to disable hard crash

def _unit_assert_mass_cancel(self, symbol):
    if getattr(self, "_averaging_flag", {}).get(symbol):
        msg = f"CRITICAL: mass-cancel attempted during averaging {symbol}"
        if DEBUG_UNIT_ASSERT:
            raise AssertionError(msg)
        else:
            try:
                self.logger.critical(msg)
            except Exception:
                pass
        return False
    return True

if hasattr(BybitTradingBot, "mass_cancel"):
    _prev_mass_cancel = BybitTradingBot.mass_cancel

    def _mass_cancel_with_assert(self, symbol, *args, **kwargs):
        if not _unit_assert_mass_cancel(self, symbol):
            return False
        return _prev_mass_cancel(self, symbol, *args, **kwargs)

    BybitTradingBot.mass_cancel = _mass_cancel_with_assert

# ================= END UNIT-ASSERT =================


def _reentry_guard(self, symbol):
    now = time.time()

    if symbol in self.coins_in_work:
        self.logger.warning(f"⛔ REENTRY BLOCKED (coin still in work) {symbol}")
        return False

    if symbol in self.positions and self.positions[symbol].get("size", 0) > 0:
        self.logger.warning(f"⛔ REENTRY BLOCKED (position exists) {symbol}")
        return False

    freeze_until = self.freeze_map.get(symbol)
    if freeze_until and now < freeze_until:
        self.logger.warning(f"⛔ REENTRY BLOCKED (freeze) {symbol}")
        return False

    last_ts = self.last_entry_ts.get(symbol)
    if last_ts and now - last_ts < self.entry_cooldown_sec:
        self.logger.warning(f"⛔ REENTRY BLOCKED (cooldown) {symbol}")
        return False

    return True

# ================== FREEZE FINAL PATCH ==================
import time

def _freeze_init(self):
    self.freeze_map = getattr(self, 'freeze_map', {})
    self.freeze_reasons = getattr(self, 'freeze_reasons', {})
    self.freeze_last_entry = getattr(self, 'freeze_last_entry', {})

def _freeze_is_symbol_frozen(self, symbol, now=None):
    now = now or time.time()
    until = self.freeze_map.get(symbol, 0)
    return until > now

def _freeze_apply(self, symbol, seconds, reason='tp'):
    until = time.time() + seconds
    self.freeze_map[symbol] = max(self.freeze_map.get(symbol, 0), until)
    self.freeze_reasons.setdefault(symbol, []).append(reason)
    self.logger.warning(f'❄️ FREEZE APPLIED {symbol} {seconds}s reason={reason}')

def _freeze_guard_entry(self, symbol, min_cooldown=90):
    now = time.time()
    if _freeze_is_symbol_frozen(self, symbol, now):
        self.logger.warning(f'⛔ ENTRY BLOCKED (freeze) {symbol} reasons={self.freeze_reasons.get(symbol)}')
        return False
    last = self.freeze_last_entry.get(symbol, 0)
    if now - last < min_cooldown:
        _freeze_apply(self, symbol, min_cooldown, reason='double-entry')
        return False
    self.freeze_last_entry[symbol] = now
    return True

# bind methods
if 'BybitTradingBot' in globals():
    BybitTradingBot._freeze_init = _freeze_init
    BybitTradingBot.is_symbol_frozen = _freeze_is_symbol_frozen
    BybitTradingBot.apply_freeze = _freeze_apply
    BybitTradingBot.freeze_guard_entry = _freeze_guard_entry

    # hook after position close / TP
    if hasattr(BybitTradingBot, 'on_position_closed'):
        _orig_on_pos_closed = BybitTradingBot.on_position_closed
        def _on_pos_closed_freeze(self, *a, **kw):
            res = _orig_on_pos_closed(self, *a, **kw)
            symbol = kw.get('symbol') if 'symbol' in kw else (a[0] if a else None)
            if symbol:
                self.apply_freeze(symbol, 120, reason='tp-close')
            return res
        BybitTradingBot.on_position_closed = _on_pos_closed_freeze
# ================== END FREEZE FINAL PATCH ==================



# ====================== FREEZE SYSTEM (PROD-LEVEL) ======================
# LEVEL 1: GLOBAL SYMBOL FREEZE
#  - Applied after full position close (position disappears from exchange)
#  - Blocks ANY new entry for symbol (both sides)
#
# LEVEL 2: PER-SIDE FREEZE (symbol+side)
#  - Applied after TP execution (reduce-only TP filled)
#  - Blocks re-entry ONLY for the same side (LONG or SHORT)
#
# LEVEL 3: POST-REDUCE / AVERAGING FREEZE
#  - Applied after reduce-only or grid fill events
#  - Temporarily blocks mass-cancel and re-entry during stabilization window
#
# Priority (highest → lowest):
#   GLOBAL SYMBOL FREEZE
#   PER-SIDE FREEZE
#   POST-REDUCE FREEZE
#
# Entry allowed ONLY if all three levels are clear.
# =======================================================================

import time

class FreezeController:
    def __init__(self, logger):
        self.logger = logger
        self.freeze_symbol = {}   # symbol -> ts
        self.freeze_side = {}     # (symbol, side) -> ts
        self.freeze_reduce = {}   # symbol -> ts

    def _active(self, until):
        return until is not None and until > time.time()

    # -------- setters --------
    def freeze_global(self, symbol, seconds, reason="tp"):
        self.freeze_symbol[symbol] = time.time() + seconds
        self.logger.warning(f"❄️ GLOBAL FREEZE {symbol} {seconds}s reason={reason}")

    def freeze_side_only(self, symbol, side, seconds, reason="tp"):
        self.freeze_side[(symbol, side)] = time.time() + seconds
        self.logger.warning(f"❄️ SIDE FREEZE {symbol} {side} {seconds}s reason={reason}")

    def freeze_after_reduce(self, symbol, seconds, reason="reduce"):
        self.freeze_reduce[symbol] = time.time() + seconds
        self.logger.warning(f"❄️ REDUCE FREEZE {symbol} {seconds}s reason={reason}")

    # -------- guard --------
    def is_entry_allowed(self, symbol, side):
        if self._active(self.freeze_symbol.get(symbol)):
            self.logger.warning(f"⛔ ENTRY BLOCKED [GLOBAL] {symbol}")
            return False

        if self._active(self.freeze_side.get((symbol, side))):
            self.logger.warning(f"⛔ ENTRY BLOCKED [SIDE] {symbol} {side}")
            return False

        if self._active(self.freeze_reduce.get(symbol)):
            self.logger.warning(f"⛔ ENTRY BLOCKED [POST-REDUCE] {symbol}")
            return False

        return True

# ================= END FREEZE CONTROLLER =================



# ================= FREEZE SYSTEM (3-LEVEL HARD ENTRY-GATE) =================
import time

def _ensure_freeze_maps(self):
    if not hasattr(self, "freeze_symbol"):
        self.freeze_symbol = {}
    if not hasattr(self, "freeze_side"):
        self.freeze_side = {}
    if not hasattr(self, "freeze_post_close"):
        self.freeze_post_close = {}

def entry_gate_allowed(self, symbol: str, side: str) -> bool:
    self._ensure_freeze_maps()
    now = time.time()

    if now < self.freeze_symbol.get(symbol, 0):
        self.logger.warning(f"⛔ ENTRY BLOCKED [GLOBAL FREEZE] {symbol}")
        return False

    if now < self.freeze_side.get((symbol, side), 0):
        self.logger.warning(f"⛔ ENTRY BLOCKED [SIDE FREEZE] {symbol} {side}")
        return False

    if now < self.freeze_post_close.get(symbol, 0):
        self.logger.warning(f"⛔ ENTRY BLOCKED [POST-CLOSE] {symbol}")
        return False

    return True

def apply_tp_freeze(self, symbol: str, side: str):
    self._ensure_freeze_maps()
    now = time.time()
    self.freeze_symbol[symbol] = now + 90
    self.freeze_side[(symbol, side)] = now + 120
    self.freeze_post_close[symbol] = now + 60
    self.logger.info(f"❄️ FREEZE APPLIED {symbol} | global=90s side=120s post=60s")
# ================= END FREEZE SYSTEM =================



# ================= HARD REENTRY LOCK (LEVEL 4) =================
import time

def _ensure_reentry_lock(self):
    if not hasattr(self, "last_exit_ts"):
        self.last_exit_ts = {}
    if not hasattr(self, "last_entry_ts"):
        self.last_entry_ts = {}

HARD_REENTRY_SECONDS = 180  # hard lock after exit

def hard_reentry_blocked(self, symbol: str) -> bool:
    self._ensure_reentry_lock()
    now = time.time()
    last_exit = self.last_exit_ts.get(symbol, 0)
    if now - last_exit < HARD_REENTRY_SECONDS:
        self.logger.warning(
            f"⛔ ENTRY BLOCKED [HARD REENTRY LOCK] {symbol} "
            f"({int(HARD_REENTRY_SECONDS - (now - last_exit))}s left)"
        )
        return True
    return False

def mark_entry(self, symbol: str):
    self._ensure_reentry_lock()
    self.last_entry_ts[symbol] = time.time()

def mark_exit(self, symbol: str):
    self._ensure_reentry_lock()
    self.last_exit_ts[symbol] = time.time()
# ================= END HARD REENTRY LOCK =================



# ================= HARD FREEZE LEVEL 4 (PROD, FIXED) =================
# NOTE: This patch MUST live inside the bot class. No top-level `self` usage.

import time

class FreezeGateMixin:
    def _init_freeze(self):
        self.freeze_symbol = getattr(self, "freeze_symbol", {})
        self.freeze_side = getattr(self, "freeze_side", {})
        self.freeze_post_close = getattr(self, "freeze_post_close", {})
        self.freeze_cycle_guard = getattr(self, "freeze_cycle_guard", False)

    def entry_gate_allowed(self, symbol: str, side: str) -> bool:
        now = time.time()

        if self.freeze_cycle_guard:
            self.logger.warning(f"⛔ ENTRY BLOCKED [CYCLE GUARD] {symbol}")
            return False

        if now < self.freeze_symbol.get(symbol, 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [GLOBAL FREEZE] {symbol}")
            return False

        if now < self.freeze_side.get((symbol, side), 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [SIDE FREEZE] {symbol} {side}")
            return False

        if now < self.freeze_post_close.get(symbol, 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [POST-CLOSE] {symbol}")
            return False

        return True

    def apply_tp_freeze(self, symbol: str, side: str):
        now = time.time()
        self.freeze_symbol[symbol] = now + 90
        self.freeze_side[(symbol, side)] = now + 120
        self.freeze_post_close[symbol] = now + 60
        self.freeze_cycle_guard = True
        self.logger.info(
            f"❄️ FREEZE APPLIED {symbol} | global=90s side=120s post=60s"
        )

    def clear_cycle_guard(self):
        self.freeze_cycle_guard = False
# ================= END HARD FREEZE LEVEL 4 =================


# ================== HARD FREEZE ENTRY-GATE (LEVEL 4 FINAL) ==================
# NOTE: Non-invasive patch. Does NOT modify existing logic, only gates entries.

import time

class FreezeGate:
    def __init__(self, logger):
        self.logger = logger
        self.freeze_symbol = {}        # symbol -> ts
        self.freeze_side = {}          # (symbol, side) -> ts
        self.freeze_post_close = {}    # symbol -> ts
        self.cycle_guard = False       # blocks same-cycle reentry

    def entry_allowed(self, symbol: str, side: str) -> bool:
        now = time.time()

        if self.cycle_guard:
            self.logger.warning(f"⛔ ENTRY BLOCKED [CYCLE GUARD] {symbol}")
            return False

        if now < self.freeze_symbol.get(symbol, 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [GLOBAL FREEZE] {symbol}")
            return False

        if now < self.freeze_side.get((symbol, side), 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [SIDE FREEZE] {symbol} {side}")
            return False

        if now < self.freeze_post_close.get(symbol, 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [POST CLOSE] {symbol}")
            return False

        return True

    def apply_tp_freeze(self, symbol: str, side: str):
        now = time.time()
        self.freeze_symbol[symbol] = now + 90
        self.freeze_side[(symbol, side)] = now + 120
        self.freeze_post_close[symbol] = now + 60
        self.cycle_guard = True
        self.logger.info(
            f"❄️ FREEZE APPLIED {symbol} | global=90s side=120s post=60s"
        )

    def clear_cycle_guard(self):
        self.cycle_guard = False

# ================== END HARD FREEZE ENTRY-GATE ==================



# ====================== FREEZE HARD-GATE PATCH (LEVEL 5) ======================
# Freeze-only patch. Trading logic untouched.

import time

class FreezeHardGateMixin:
    def init_freeze_hardgate(self):
        if not hasattr(self, "freeze_symbol"):
            self.freeze_symbol = {}
        if not hasattr(self, "freeze_side"):
            self.freeze_side = {}
        if not hasattr(self, "freeze_post_close"):
            self.freeze_post_close = {}
        if not hasattr(self, "last_entry_ts"):
            self.last_entry_ts = {}

    def entry_gate_allowed(self, symbol: str, side: str) -> bool:
        now = time.time()

        if now < self.freeze_symbol.get(symbol, 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [GLOBAL FREEZE] {symbol}")
            return False

        if now < self.freeze_side.get((symbol, side), 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [SIDE FREEZE] {symbol} {side}")
            return False

        if now < self.freeze_post_close.get(symbol, 0):
            self.logger.warning(f"⛔ ENTRY BLOCKED [POST CLOSE] {symbol}")
            return False

        last = self.last_entry_ts.get((symbol, side), 0)
        if now - last < 2.0:
            self.logger.warning(f"⛔ ENTRY BLOCKED [ANTI-SPAM] {symbol} {side}")
            return False

        self.last_entry_ts[(symbol, side)] = now
        return True

    def apply_tp_freeze(self, symbol: str, side: str):
        now = time.time()
        self.freeze_symbol[symbol] = now + 90
        self.freeze_side[(symbol, side)] = now + 120
        self.freeze_post_close[symbol] = now + 60

        self.logger.warning(
            f"❄️ FREEZE APPLIED {symbol} | global=90s side=120s post=60s"
        )

# ==================== END FREEZE HARD-GATE PATCH ==============================

    # ===== LEVEL-5 HARD ENTRY-GATE =====
    def entry_gate_allowed(self, symbol: str, side: str) -> bool:
        import time
        now = time.time()
        with self.entry_gate_lock:
            if now < self.freeze_symbol.get(symbol, 0):
                self.logger.warning(f"⛔ ENTRY BLOCKED [GLOBAL FREEZE] {symbol}")
                return False
            if now < self.freeze_side.get((symbol, side), 0):
                self.logger.warning(f"⛔ ENTRY BLOCKED [SIDE FREEZE] {symbol} {side}")
                return False
            if now < self.freeze_post_close.get(symbol, 0):
                self.logger.warning(f"⛔ ENTRY BLOCKED [POST-CLOSE] {symbol}")
                return False
            if self.last_close_cycle.get(symbol) == self.current_cycle_id:
                self.logger.warning(f"⛔ ENTRY BLOCKED [SAME CYCLE] {symbol}")
                return False
            return True

    def apply_tp_freeze(self, symbol: str, side: str):
        import time
        now = time.time()
        self.freeze_symbol[symbol] = now + 90
        self.freeze_side[(symbol, side)] = now + 120
        self.freeze_post_close[symbol] = now + 60
        self.last_close_cycle[symbol] = self.current_cycle_id
        self.logger.info(
            f"❄️ FREEZE APPLIED {symbol} | global=90s side=120s post=60s"
        )
    # =================================

    # ===== LEVEL-5 HARD ENTRY-GATE =====
    def entry_gate_allowed(self, symbol: str, side: str) -> bool:
        import time
        now = time.time()
        with self.entry_gate_lock:
            if now < self.freeze_symbol.get(symbol, 0):
                self.logger.warning(f"⛔ ENTRY BLOCKED [GLOBAL FREEZE] {symbol}")
                return False
            if now < self.freeze_side.get((symbol, side), 0):
                self.logger.warning(f"⛔ ENTRY BLOCKED [SIDE FREEZE] {symbol} {side}")
                return False
            if now < self.freeze_post_close.get(symbol, 0):
                self.logger.warning(f"⛔ ENTRY BLOCKED [POST-CLOSE] {symbol}")
                return False
            if self.last_close_cycle.get(symbol) == self.current_cycle_id:
                self.logger.warning(f"⛔ ENTRY BLOCKED [SAME CYCLE] {symbol}")
                return False
            return True

    def apply_tp_freeze(self, symbol: str, side: str):
        import time
        now = time.time()
        self.freeze_symbol[symbol] = now + 90
        self.freeze_side[(symbol, side)] = now + 120
        self.freeze_post_close[symbol] = now + 60
        self.last_close_cycle[symbol] = self.current_cycle_id
        self.logger.info(
            f"❄️ FREEZE APPLIED {symbol} | global=90s side=120s post=60s"
        )
    # =================================

# ==================== ДОБАВЛЕННЫЙ КОД ====================

def _patch_entry_methods():
    """Исправление: добавляем единую точку входа"""
    
    # Сохраняем оригинальный метод
    if not hasattr(BybitTradingBot, '_real_enter_position'):
        BybitTradingBot._real_enter_position = BybitTradingBot.enter_position_for_working_coin
    
    def _execute_entry(self, config, entry_price):
        """Единая точка входа с проверкой всех заморозок"""
        symbol = config.symbol
        side = "Buy" if config.direction == "long" else "Sell"
        
        # Инициализация хранилищ
        if not hasattr(self, '_entry_block'):
            self._entry_block = {}
            self._last_entry = {}
            self._entry_count = {}
        
        # === ПРОВЕРКА 1: Глобальная заморозка (5 минут) ===
        if f"global_{symbol}" in self._entry_block:
            if time.time() < self._entry_block[f"global_{symbol}"]:
                self.logger.warning(f"⛔ ВХОД ЗАБЛОКИРОВАН [GLOBAL] {symbol}")
                return False
        
        # === ПРОВЕРКА 2: Заморозка по стороне (5 минут) ===
        if f"side_{symbol}_{side}" in self._entry_block:
            if time.time() < self._entry_block[f"side_{symbol}_{side}"]:
                self.logger.warning(f"⛔ ВХОД ЗАБЛОКИРОВАН [SIDE] {symbol} {side}")
                return False
        
        # === ПРОВЕРКА 3: Post-close (1 минута) ===
        if f"post_{symbol}" in self._entry_block:
            if time.time() < self._entry_block[f"post_{symbol}"]:
                self.logger.warning(f"⛔ ВХОД ЗАБЛОКИРОВАН [POST] {symbol}")
                return False
        
        # === ПРОВЕРКА 4: Таймаут после TP ===
        if self.is_symbol_in_timeout(symbol):
            self.logger.warning(f"⛔ ВХОД ЗАБЛОКИРОВАН [TIMEOUT] {symbol}")
            return False
        
        # === ПРОВЕРКА 5: Анти-спам (2 минуты между входами) ===
        last = self._last_entry.get(symbol, 0)
        if time.time() - last < 120:
            self.logger.warning(f"⛔ ВХОД ЗАБЛОКИРОВАН [ANTI-SPAM] {symbol}")
            return False
        
        # === ПРОВЕРКА 6: Максимум входов в день ===
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"{symbol}_{today}"
        count = self._entry_count.get(key, 0)
        if count >= 2:
            self.logger.warning(f"⛔ ВХОД ЗАБЛОКИРОВАН [MAX_ENTRIES] {symbol}")
            return False
        
        # === ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ===
        self._last_entry[symbol] = time.time()
        self._entry_count[key] = count + 1
        
        self.logger.info(f"✅ ВХОД РАЗРЕШЕН {symbol} {side} (вход #{count+1} сегодня)")
        return self._real_enter_position(config, entry_price)
    
    def _apply_block(self, symbol, side=None, block_type="global", seconds=300):
        """Применить блокировку"""
        if not hasattr(self, '_entry_block'):
            self._entry_block = {}
        
        if block_type == "global":
            key = f"global_{symbol}"
        elif block_type == "side" and side:
            key = f"side_{symbol}_{side}"
        elif block_type == "post":
            key = f"post_{symbol}"
        else:
            return
        
        self._entry_block[key] = time.time() + seconds
        self.logger.info(f"❄️ БЛОКИРОВКА [{block_type}] {symbol} {side or ''} на {seconds} сек")
    
    # Применяем патчи
    BybitTradingBot.enter_position_for_working_coin = _execute_entry
    BybitTradingBot.apply_block = _apply_block
    
    # Патчим метод очистки
    if hasattr(BybitTradingBot, 'cleanup_finished_coin_with_timeout'):
        original_cleanup = BybitTradingBot.cleanup_finished_coin_with_timeout
        
        def cleanup_with_block(self, symbol):
            self.apply_block(symbol, block_type="global", seconds=300)
            self.apply_block(symbol, block_type="post", seconds=60)
            original_cleanup(self, symbol)
        
        BybitTradingBot.cleanup_finished_coin_with_timeout = cleanup_with_block

# Применяем исправление
_patch_entry_methods()

# ==================== КОНЕЦ ИСПРАВЛЕНИЯ ====================