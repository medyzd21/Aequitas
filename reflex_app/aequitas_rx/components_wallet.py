"""Wallet + on-chain UI components — additive to components.py.

The pieces here plug into existing pages:

* `wallet_badge()` — compact wallet chip for the navbar (connect / switch).
* `protocol_status_banner()` — top strip showing wallet, network,
  deployment registry, and the latest on-chain action in one glance.
* `confirm_drawer()` — modal confirmation card shown before any signed
  transaction. Plain-English summary at the top, raw technical details
  collapsed inside an "Advanced" accordion.
* `action_card_v2()` — richer, role-aware card used on the Actions page.
* `role_column()` — simple grouping column with a heading + icon.
* `wallet_event_bridge()` — invisible DOM bridge. Forwards the JS-side
  `aequitas:wallet` and `aequitas:tx` CustomEvents into Reflex by
  programmatically clicking hidden buttons.

All components read from `AppState` only — no new state lives here.
"""
from __future__ import annotations

import reflex as rx

from .components import pill
from .state import AppState
from .theme import CARD_STYLE, PALETTE, PILL_STYLES, RIBBON_STYLE


# ==========================================================================
# Hidden event bridge — JS CustomEvent → Reflex handler
# ==========================================================================
_WALLET_EVENT_LISTENER_JS = """
(function () {
  if (window.__aequitasWalletListenerInstalled) return;
  window.__aequitasWalletListenerInstalled = true;
  const click = (id) => {
    const btn = document.getElementById(id);
    if (btn) btn.click();
  };
  const syncWallet = () => click("__aequitas_refresh_wallet");
  const syncTx = (event) => {
    const hash = event && event.detail && event.detail.hash;
    if (!hash) return;
    window.__aequitasLastConfirmedTx = String(hash);
    window.__aequitasLastConfirmedTxReceipt = event.detail;
    click("__aequitas_tx_confirmed");
  };
  window.addEventListener("aequitas:wallet", syncWallet);
  window.addEventListener("aequitas:tx", syncTx);
  // First-load sync: once the bridge is ready, sync state once.
  let tries = 0;
  const tick = () => {
    if (window.aequitasWallet && window.aequitasWallet.getState) {
      syncWallet();
      return;
    }
    if (tries++ < 40) setTimeout(tick, 50);
  };
  setTimeout(tick, 50);
})();
"""


def wallet_event_bridge() -> rx.Component:
    """Invisible DOM bridge that forwards wallet and tx events from the
    JS bridge back into Reflex state handlers.

    Rendered on pages that need live wallet status updates.
    """
    return rx.box(
        rx.script(_WALLET_EVENT_LISTENER_JS),
        rx.button(
            "refresh-wallet",
            id="__aequitas_refresh_wallet",
            on_click=AppState.refresh_wallet_state,
            style={
                "position": "fixed",
                "left": "-9999px",
                "top": "-9999px",
                "width": "1px",
                "height": "1px",
                "opacity": "0",
                "pointer_events": "none",
            },
        ),
        rx.button(
            "confirm-tx",
            id="__aequitas_tx_confirmed",
            on_click=AppState.refresh_tx_confirmation,
            style={
                "position": "fixed",
                "left": "-9999px",
                "top": "-9999px",
                "width": "1px",
                "height": "1px",
                "opacity": "0",
                "pointer_events": "none",
            },
        ),
        aria_hidden="true",
    )


# ==========================================================================
# Wallet badge — fits inside the navbar
# ==========================================================================
def _wallet_badge_connected() -> rx.Component:
    return rx.hstack(
        # Status dot
        rx.box(
            style={
                "width": "8px", "height": "8px",
                "border_radius": "50%",
                "background": rx.cond(
                    AppState.wallet_is_sepolia,
                    PALETTE["good"], PALETTE["warn"],
                ),
                "box_shadow": "0 0 4px rgba(255,255,255,0.3)",
            },
        ),
        rx.text(
            AppState.wallet_short,
            style={"color": PALETTE["text"], "font_size": "12px",
                   "font_family": "ui-monospace, SFMono-Regular, monospace",
                   "font_weight": "500"},
        ),
        rx.match(
            AppState.wallet_pill,
            ("good", pill("SEPOLIA", "good")),
            ("warn", pill("WRONG NET", "warn")),
            pill("WALLET", "muted"),
        ),
        rx.cond(
            ~AppState.wallet_is_sepolia,
            rx.button(
                "Switch",
                on_click=AppState.switch_to_sepolia,
                size="1",
                color_scheme="amber",
                variant="soft",
            ),
            rx.fragment(),
        ),
        rx.button(
            "Disconnect",
            on_click=AppState.disconnect_wallet,
            size="1",
            variant="ghost",
            color_scheme="gray",
        ),
        spacing="2",
        align="center",
        style={
            "padding": "4px 10px",
            "background": PALETTE["panel"],
            "border": f"1px solid {PALETTE['edge']}",
            "border_radius": "8px",
        },
    )


def _wallet_badge_disconnected() -> rx.Component:
    return rx.button(
        rx.hstack(
            rx.box(
                style={
                    "width": "8px", "height": "8px",
                    "border_radius": "50%",
                    "background": PALETTE["muted"],
                },
            ),
            rx.text("Connect wallet",
                    style={"font_size": "12px", "font_weight": "500"}),
            spacing="2",
            align="center",
        ),
        on_click=AppState.connect_wallet,
        size="1",
        color_scheme="cyan",
        variant="soft",
    )


def wallet_badge() -> rx.Component:
    return rx.cond(
        AppState.wallet_connected,
        _wallet_badge_connected(),
        _wallet_badge_disconnected(),
    )


# ==========================================================================
# Protocol status banner — top strip on the Actions page (and optionally
# globally, if added to shell()).
# ==========================================================================
def _status_tile(label: str, value: rx.Component, sub: rx.Component | str = "") -> rx.Component:
    if isinstance(sub, str):
        sub_comp = rx.text(
            sub,
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_top": "4px"},
        )
    else:
        sub_comp = sub
    return rx.box(
        rx.text(
            label,
            style={"color": PALETTE["muted"], "font_size": "10px",
                   "letter_spacing": "0.08em", "text_transform": "uppercase",
                   "margin_bottom": "4px"},
        ),
        value,
        sub_comp,
        style={
            **CARD_STYLE,
            "flex": "1 1 0",
            "min_width": "180px",
        },
    )


def protocol_status_banner() -> rx.Component:
    return rx.box(
        rx.hstack(
            # --- Wallet ---
            _status_tile(
                "Wallet",
                rx.hstack(
                    rx.match(
                        AppState.wallet_pill,
                        ("good", pill("SEPOLIA", "good")),
                        ("warn", pill("WRONG NETWORK", "warn")),
                        pill("NOT CONNECTED", "muted"),
                    ),
                    rx.cond(
                        AppState.wallet_connected,
                        rx.text(AppState.wallet_short,
                                style={"color": PALETTE["text"],
                                       "font_size": "12px",
                                       "font_family": "ui-monospace, monospace"}),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.text(AppState.wallet_status_message,
                        style={"color": PALETTE["muted"], "font_size": "11px",
                               "margin_top": "4px"}),
            ),
            # --- Network ---
            _status_tile(
                "Network",
                rx.text(
                    rx.cond(
                        AppState.wallet_connected,
                        AppState.wallet_chain_name,
                        "—",
                    ),
                    style={"color": PALETTE["text"], "font_size": "14px",
                           "font_weight": "600"},
                ),
                rx.cond(
                    AppState.wallet_connected & ~AppState.wallet_is_sepolia,
                    rx.button(
                        "Switch to Sepolia",
                        on_click=AppState.switch_to_sepolia,
                        size="1", color_scheme="amber", variant="soft",
                        margin_top="4px",
                    ),
                    rx.text(
                        rx.cond(
                            AppState.wallet_is_sepolia,
                            "Testnet · safe to practise",
                            "Connect to see network",
                        ),
                        style={"color": PALETTE["muted"], "font_size": "11px",
                               "margin_top": "4px"},
                    ),
                ),
            ),
            # --- Deployment registry ---
            _status_tile(
                "Deployment",
                rx.hstack(
                    rx.match(
                        AppState.deployment_pill,
                        ("good", pill("VERIFIED · SEPOLIA", "good")),
                        ("warn", pill("ON SEPOLIA", "warn")),
                        ("muted", pill("NOT DEPLOYED", "muted")),
                        pill("UNKNOWN", "muted"),
                    ),
                    spacing="2",
                ),
                rx.text(
                    rx.cond(
                        AppState.registry_present,
                        AppState.registry_deployed_at,
                        "Run the deploy script to connect",
                    ),
                    style={"color": PALETTE["muted"], "font_size": "11px",
                           "margin_top": "4px"},
                ),
            ),
            # --- Last on-chain action ---
            _status_tile(
                "Last action",
                rx.hstack(
                    rx.match(
                        AppState.tx_pill,
                        ("good", pill("CONFIRMED", "good")),
                        ("warn", pill("PENDING",   "warn")),
                        ("bad",  pill("FAILED",    "bad")),
                        pill("IDLE", "muted"),
                    ),
                    rx.cond(
                        AppState.last_tx_short != "",
                        rx.text(AppState.last_tx_short,
                                style={"color": PALETTE["text"],
                                       "font_size": "11px",
                                       "font_family": "ui-monospace, monospace"}),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    AppState.last_tx_explorer_url != "",
                    rx.link(
                        "View on Etherscan →",
                        href=AppState.last_tx_explorer_url,
                        is_external=True,
                        style={"color": PALETTE["accent"], "font_size": "11px",
                               "margin_top": "4px"},
                    ),
                    rx.text(
                        rx.cond(
                            AppState.last_tx_action != "",
                            AppState.last_tx_action,
                            "No recent action",
                        ),
                        style={"color": PALETTE["muted"], "font_size": "11px",
                               "margin_top": "4px"},
                    ),
                ),
            ),
            spacing="3",
            width="100%",
            align="stretch",
            wrap="wrap",
        ),
        style={"margin_bottom": "14px"},
    )


# ==========================================================================
# Confirmation drawer — pre-signing card for every action
# ==========================================================================
def _param_rows() -> rx.Component:
    return rx.vstack(
        rx.foreach(
            AppState.confirm_params_rows,
            lambda row: rx.hstack(
                rx.text(row["key"],
                        style={"color": PALETTE["muted"], "font_size": "11px",
                               "min_width": "140px"}),
                rx.code(row["value"],
                        style={"color": PALETTE["text"], "font_size": "11px"}),
                spacing="2",
                align="center",
            ),
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )


def _confirm_body() -> rx.Component:
    return rx.vstack(
        # --- Header ---
        rx.hstack(
            rx.heading(AppState.confirm_action_label, size="4",
                       style={"color": PALETTE["text"]}),
            rx.spacer(),
            rx.cond(
                AppState.confirm_is_live,
                pill("LIVE ON SEPOLIA", "good"),
                pill("OFF-CHAIN", "muted"),
            ),
            align="center",
            width="100%",
        ),
        rx.text(
            rx.cond(
                AppState.confirm_is_live,
                "This action will be written to the on-chain audit trail once signed.",
                "This step stays off-chain and records your acknowledgement in the demo timeline.",
            ),
            style={"color": PALETTE["muted"], "font_size": "12px",
                   "margin_top": "4px"},
        ),
        # --- Plain-English summary ---
        rx.box(
            rx.text(AppState.confirm_summary,
                    style={"color": PALETTE["text"], "font_size": "13px",
                           "line_height": "1.55"}),
            style={**CARD_STYLE,
                   "border_left": f"3px solid {PALETTE['accent']}",
                   "margin_top": "10px"},
        ),
        # --- Dual meaning ---
        rx.hstack(
            rx.box(
                rx.text("Actuarial meaning",
                        style={"color": PALETTE["accent"], "font_size": "10px",
                               "letter_spacing": "0.08em",
                               "text_transform": "uppercase",
                               "margin_bottom": "4px"}),
                rx.text(AppState.confirm_actuarial,
                        style={"color": PALETTE["text"], "font_size": "12px",
                               "line_height": "1.5"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                rx.text("Protocol meaning",
                        style={"color": PALETTE["accent"], "font_size": "10px",
                               "letter_spacing": "0.08em",
                               "text_transform": "uppercase",
                               "margin_bottom": "4px"}),
                rx.text(AppState.confirm_protocol,
                        style={"color": PALETTE["muted"], "font_size": "12px",
                               "line_height": "1.5"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            align="stretch",
            margin_top="10px",
        ),
        # --- Reversibility line ---
        rx.box(
            rx.hstack(
                pill("REVERSIBILITY", "warn"),
                rx.text(AppState.confirm_reversible,
                        style={"color": PALETTE["muted"], "font_size": "12px"}),
                spacing="3",
                align="center",
            ),
            style={**RIBBON_STYLE, "margin_top": "10px",
                   "border_left": f"3px solid {PALETTE['warn']}"},
        ),
        # --- Advanced / technical details ---
        rx.accordion.root(
            rx.accordion.item(
                header=rx.text("Advanced · technical details",
                               style={"color": PALETTE["muted"],
                                      "font_size": "11px"}),
                content=rx.box(
                    _param_rows(),
                    rx.cond(
                        AppState.confirm_target_addr != "",
                        rx.hstack(
                            rx.text("On-chain address",
                                    style={"color": PALETTE["muted"],
                                           "font_size": "11px",
                                           "min_width": "140px"}),
                            rx.code(AppState.confirm_target_addr,
                                    style={"color": PALETTE["text"],
                                           "font_size": "11px"}),
                            spacing="2",
                            align="center",
                            margin_top="8px",
                        ),
                        rx.fragment(),
                    ),
                    style={"padding_top": "8px"},
                ),
                value="adv",
            ),
            collapsible=True,
            type="single",
            width="100%",
            margin_top="10px",
        ),
        # --- Buttons ---
        rx.hstack(
            rx.spacer(),
            rx.button("Cancel", on_click=AppState.close_action,
                      variant="soft", color_scheme="gray"),
            rx.button(
                rx.cond(
                    AppState.confirm_is_live,
                    "Sign in MetaMask",
                    "Acknowledge and continue",
                ),
                on_click=AppState.confirm_action,
                color_scheme="cyan",
                disabled=rx.cond(
                    AppState.confirm_is_live,
                    ~AppState.can_run_live_action,
                    False,
                ),
            ),
            spacing="2",
            width="100%",
            margin_top="14px",
        ),
        # Blocker line (only rendered if a live action is gated)
        rx.cond(
            AppState.confirm_is_live & ~AppState.can_run_live_action,
            rx.box(
                rx.hstack(
                    pill("BLOCKED", "bad"),
                    rx.text(AppState.live_action_blocker,
                            style={"color": PALETTE["muted"],
                                   "font_size": "12px"}),
                    spacing="3",
                    align="center",
                ),
                style={**RIBBON_STYLE,
                       "border_left": f"3px solid {PALETTE['bad']}",
                       "margin_top": "10px"},
            ),
            rx.fragment(),
        ),
        spacing="2",
        width="100%",
    )


def confirm_drawer() -> rx.Component:
    """Rendered once at the page level — visible only when
    `AppState.confirm_open` is true."""
    return rx.cond(
        AppState.confirm_open,
        rx.box(
            # Backdrop
            rx.box(
                on_click=AppState.close_action,
                style={
                    "position": "fixed", "top": 0, "left": 0, "right": 0, "bottom": 0,
                    "background": "rgba(0,0,0,0.55)",
                    "z_index": "900",
                },
            ),
            # Panel
            rx.box(
                _confirm_body(),
                style={
                    "position": "fixed",
                    "top":    "50%",
                    "left":   "50%",
                    "transform": "translate(-50%, -50%)",
                    "background":    PALETTE["panel"],
                    "border":        f"1px solid {PALETTE['edge']}",
                    "border_radius": "12px",
                    "padding":       "22px 24px",
                    "width":         "min(720px, calc(100vw - 40px))",
                    "max_height":    "85vh",
                    "overflow_y":    "auto",
                    "box_shadow":    "0 20px 80px rgba(0,0,0,0.6)",
                    "z_index":       "1000",
                },
            ),
        ),
        rx.fragment(),
    )


# ==========================================================================
# Role column + action card for the Actions page
# ==========================================================================
def role_column(
    title: str,
    role_tag: str,
    blurb: str,
    children: list[rx.Component],
) -> rx.Component:
    return rx.box(
        rx.hstack(
            pill(role_tag.upper(), "muted"),
            rx.heading(title, size="4", style={"color": PALETTE["text"]}),
            spacing="3",
            align="center",
        ),
        rx.text(blurb,
                style={"color": PALETTE["muted"], "font_size": "12px",
                       "margin_top": "4px", "margin_bottom": "10px",
                       "line_height": "1.5"}),
        rx.vstack(
            *children,
            spacing="2",
            align="stretch",
            width="100%",
        ),
        style={**CARD_STYLE, "min_width": "260px", "flex": "1 1 0"},
    )


def action_card_v2(
    action_key: str,
    label: str,
    one_liner: str,
    mode_tag: str,
    target_contract: str,
) -> rx.Component:
    """Clickable card for the Actions page. Opens the confirmation drawer
    rather than firing the action directly — that separation is the whole
    point of the UX."""
    is_var_tag = hasattr(mode_tag, "contains")
    mode_label = mode_tag.upper()
    mode_badge = (
        rx.cond(
            mode_label.contains("LIVE"),
            pill(mode_label, "good"),
            pill(mode_label, "muted"),
        )
        if is_var_tag
        else pill(mode_label, "good" if "LIVE" in mode_label else "muted")
    )
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(label,
                        style={"color": PALETTE["text"], "font_size": "14px",
                               "font_weight": "600"}),
                rx.text(one_liner,
                        style={"color": PALETTE["muted"], "font_size": "12px",
                               "line_height": "1.45"}),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.vstack(
                mode_badge,
                rx.text(target_contract,
                        style={"color": PALETTE["muted"],
                               "font_size": "10px",
                               "letter_spacing": "0.06em",
                               "text_transform": "uppercase"}),
                spacing="1",
                align="end",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        on_click=AppState.open_action(action_key),
        style={
            **CARD_STYLE,
            "cursor": "pointer",
            "transition": "all 120ms ease",
            "_hover": {
                "border": f"1px solid {PALETTE['accent']}",
                "background": "#13203a",
            },
        },
    )


# ==========================================================================
# Connect prompt (shown on Actions page when wallet is missing)
# ==========================================================================
def _wallet_error_strip() -> rx.Component:
    """Renders `AppState.wallet_last_error` as a red ribbon so a failed
    MetaMask handshake is visible instead of silent."""
    return rx.cond(
        AppState.wallet_last_error != "",
        rx.box(
            rx.hstack(
                pill("WALLET ERROR", "bad"),
                rx.text(
                    AppState.wallet_last_error,
                    style={"color": PALETTE["text"], "font_size": "12px",
                           "line_height": "1.5"},
                ),
                rx.spacer(),
                rx.button(
                    "Retry",
                    on_click=AppState.connect_wallet,
                    color_scheme="cyan",
                    variant="soft",
                    size="1",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            style={**RIBBON_STYLE,
                   "border_left": f"3px solid {PALETTE['bad']}",
                   "margin_bottom": "8px"},
        ),
        rx.fragment(),
    )


def connect_prompt() -> rx.Component:
    return rx.vstack(
        # Surface any recent wallet error regardless of connection state —
        # a connection rejected by the user still deserves a visible hint.
        _wallet_error_strip(),
        rx.cond(
            ~AppState.wallet_connected,
            rx.box(
                rx.hstack(
                    pill("WALLET REQUIRED", "warn"),
                    rx.text(
                        "Connect a MetaMask wallet on Sepolia to sign the "
                        "live actions below. You can still explore the "
                        "off-chain actions without connecting.",
                        style={"color": PALETTE["muted"], "font_size": "12px",
                               "line_height": "1.5"},
                    ),
                    rx.spacer(),
                    rx.button(
                        "Connect MetaMask",
                        on_click=AppState.connect_wallet,
                        color_scheme="cyan",
                        size="2",
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                style={**RIBBON_STYLE,
                       "border_left": f"3px solid {PALETTE['warn']}",
                       "margin_bottom": "14px"},
            ),
            rx.cond(
                ~AppState.wallet_is_sepolia,
                rx.box(
                    rx.hstack(
                        pill("SWITCH NETWORK", "warn"),
                        rx.text(
                            "Your wallet is connected but not on Sepolia. "
                            "Live actions are disabled until you switch.",
                            style={"color": PALETTE["muted"],
                                   "font_size": "12px"},
                        ),
                        rx.spacer(),
                        rx.button(
                            "Switch to Sepolia",
                            on_click=AppState.switch_to_sepolia,
                            color_scheme="amber",
                            size="2",
                        ),
                        spacing="3",
                        align="center",
                        width="100%",
                    ),
                    style={**RIBBON_STYLE,
                           "border_left": f"3px solid {PALETTE['warn']}",
                           "margin_bottom": "14px"},
                ),
                rx.fragment(),
            ),
        ),
        spacing="2",
        align="stretch",
        width="100%",
    )
