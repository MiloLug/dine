import Foundation
import OSLog
import SQLite3

private let log = Logger(subsystem: "dev.dine.Dine", category: "library")

struct DineApp: Identifiable {
    let id: Int64
    let name: String
}

/// The user's app list, persisted in `Application Support/dine.sqlite`.
/// SQLite rather than SwiftData: `@Model` needs Apple's closed SwiftDataMacros, which can't
/// expand on the Linux toolchain.
@MainActor
final class AppLibrary: ObservableObject {
    @Published private(set) var apps: [DineApp] = []

    // Lives as long as the app, so it's never closed.
    private var db: OpaquePointer?

    init() {
        do {
            let dir = try FileManager.default.url(
                for: .applicationSupportDirectory, in: .userDomainMask,
                appropriateFor: nil, create: true)
            let path = dir.appendingPathComponent("dine.sqlite").path
            guard sqlite3_open_v2(path, &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nil) == SQLITE_OK else {
                throw DBError(message: errorMessage())
            }
            try exec("CREATE TABLE IF NOT EXISTS apps(id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            apps = try loadApps()
            log.notice("loaded \(self.apps.count) apps")
        } catch {
            log.error("db unavailable: \(String(describing: error), privacy: .public)")
            sqlite3_close(db)
            db = nil
        }
    }

    func add(name: String) {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, db != nil else { return }
        do {
            let stmt = try prepare("INSERT INTO apps(name) VALUES (?)")
            defer { sqlite3_finalize(stmt) }
            // SQLITE_TRANSIENT (SQLite copies the string); the C macro isn't imported into Swift.
            let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
            sqlite3_bind_text(stmt, 1, name, -1, transient)
            guard sqlite3_step(stmt) == SQLITE_DONE else { throw DBError(message: errorMessage()) }
            let app = DineApp(id: sqlite3_last_insert_rowid(db), name: name)
            apps.append(app)
            log.notice("added app \(name, privacy: .public) id \(app.id)")
        } catch {
            log.error("add failed: \(String(describing: error), privacy: .public)")
        }
    }

    private func loadApps() throws -> [DineApp] {
        let stmt = try prepare("SELECT id, name FROM apps ORDER BY id")
        defer { sqlite3_finalize(stmt) }
        var result: [DineApp] = []
        while true {
            switch sqlite3_step(stmt) {
            case SQLITE_ROW:
                result.append(DineApp(
                    id: sqlite3_column_int64(stmt, 0),
                    name: sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""))
            case SQLITE_DONE:
                return result
            default:
                throw DBError(message: errorMessage())
            }
        }
    }

    private func exec(_ sql: String) throws {
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else {
            throw DBError(message: errorMessage())
        }
    }

    private func prepare(_ sql: String) throws -> OpaquePointer? {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw DBError(message: errorMessage())
        }
        return stmt
    }

    private func errorMessage() -> String {
        db.map { String(cString: sqlite3_errmsg($0)) } ?? "out of memory"
    }
}

private struct DBError: Error, CustomStringConvertible {
    let message: String
    var description: String { message }
}
