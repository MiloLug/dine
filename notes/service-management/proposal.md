# Service management: proposal

Letting the user choose which Android apps run as services: start at login on Linux or when Dine
starts on iOS, stop, restart after a crash, show their state. A proposal, not planned and not
part of multi-app support: those stages start an app only when it is opened or called
(`notes/multi-app-support/design.md`), and their bar for services is that microG started by hand
serves an app started after it. Tracked as [ATL-30](../general-todo.md#atl-30); alarms of apps that
aren't running are [ATL-29](../general-todo.md#atl-29).

## The request

The user's words: "let's add complete service management capability. So like... I guess, for this,
we'll need a new kind of slot - service management slot. On linux WITH SYSTEMD it will be native
systemd use with --user space, on iOS (and other platforms where everything is packed like this) -
it will be some kind of internal service manager." And: "it to have some UI to control dine's
services, that would enable or disable apps-services in systemd. So let's say we have Some Server,
and dine will enable com.mycompany.someserver service in systemd for it."

No package gets special treatment ("no special treatment for microG (system flags or whatever)"):
every app starts disabled, and microG is enabled the way any other app is.

## A slot

A new slot in dine-atl (`src/slots/`, next to `gfx`, `host`, `loop`, `ui`). Its proposed name is
`supervisor`, since "service manager" is already Android's binder registry (`ServiceManager`) and
`notes/service-impl.md` uses "services" for system services such as the vibrator.

| Backend | Where | Enabling an app | Start, stop, state |
|---|---|---|---|
| `systemd` | Linux with a systemd user manager | an instance of one template unit, enabled into the graphical session | `systemctl --user` |
| `xdg-autostart` | Linux desktops without systemd | a `.desktop` file in `~/.config/autostart` (the freedesktop autostart spec) | the app's own lock and socket; no restart |
| `internal` | iOS, and any backend where every app lives in one process | a row in the registry | Dine's running apps list |
| `none` | headless tests | nothing | nothing starts unless opened or called |

`xdg-autostart` follows the rule in `notes/multi-app-support/design.md` "Platform mechanisms": the
standard mechanism where the OS has one.

## systemd

What the local man pages state (systemd 262): template units serve "as the definition of multiple
services" (`systemd.unit`); `graphical-session.target` "is active whenever any graphical session
is running", and services that need it carry `PartOf=graphical-session.target`
(`systemd.special`); `loginctl enable-linger` starts a user manager at boot and keeps it after
logout; `systemctl freeze` and `thaw` stop and resume a unit's processes.

Proposed:
- One template unit per prefix, its instance the package: `atl-<prefix id>@<pkg>.service` runs
  `android-translation-layer --package %i` with that prefix. The prefix id keeps two prefixes'
  units apart (prefix: `notes/multi-app-support/design.md` "Prefix").
- `WantedBy=` and `PartOf=graphical-session.target`: the gtk build opens a display, so an enabled
  app starts with the graphical session, not at boot. Starting at boot needs linger and a build that
  runs without a display; open.
- `Restart=on-failure` with a start limit, so a crashing app restarts with a backoff and then stops.
- The multi-app lifetime rule still holds: an enabled app with no activity, service or client exits
  when idle, and systemd counts that as a clean stop.
- Logs go to the journal.

Later options on the same backend: socket activation of the app's socket in the runtime dir, so a
connect starts the app through systemd instead of the static model's exec; transient timers
(`systemd-run --user --on-calendar`) for alarms of apps that aren't running (ATL-29); `freeze` and
`thaw` for background apps; per-app resource limits (`MemoryMax=`).

## internal

- Dine starts the enabled apps after its launcher is up, each in its own app record of the shared
  VM.
- A crashed app restarts with a backoff, then stays crashed in the running apps list.
- Enabled apps take memory in the shared VM from Dine's start. Whether memory pressure may freeze
  or drop them like other background apps, or only after them, is open.
- iOS suspends Dine in the background, so an enabled app runs only while Dine runs, unless one of
  the mechanisms in `notes/background-processes.md` keeps it going.

## UI

- Linux: a command first (proposed, not implemented): `android-translation-layer --service
  list|enable|disable|start|stop <pkg>`, then a settings window.
- iOS: a Services screen in Dine's settings, one switch and one state per app.
- Open: whether the list shows every installed app, or only apps with a service or a boot
  receiver.

## BOOT_COMPLETED

Android sends `BOOT_COMPLETED` once per boot to apps that hold `RECEIVE_BOOT_COMPLETED`, and apps
schedule their alarms and jobs again in it (Android knowledge, unsourced here). Proposed: an
enabled app gets it when the supervisor starts it. Open: whether other apps get it at their first
start in a session.
