import Foundation

/// Connects to the Python agent's Unix socket (pc-agent/ui_bridge.py), turns its
/// events into pill states, and sends Yes/No clicks back. Reconnects forever, so
/// the app can start before the agent or outlive a restart of it.
final class BridgeClient {
    private let path: String
    private let model: PillModel
    private var fd: Int32 = -1
    private let lock = NSLock()
    private var reportedFailure = false

    init(path: String, model: PillModel) {
        self.path = path
        self.model = model
    }

    static func defaultPath() -> String {
        ProcessInfo.processInfo.environment["ASH_UI_SOCKET"] ?? NSHomeDirectory() + "/.ash/ash.sock"
    }

    func start() {
        Thread { [self] in
            while true {
                if let socketFD = connectToAgent() {
                    lock.lock(); fd = socketFD; lock.unlock()
                    log("connected to the agent")
                    readEvents(from: socketFD)
                    lock.lock(); fd = -1; lock.unlock()
                    close(socketFD)
                    log("agent disconnected")
                    model.apply(.idle, immediate: true)
                }
                Thread.sleep(forTimeInterval: 1)
            }
        }.start()
    }

    /// A click on Yes/No, sent to the agent. The agent decides whether it counts.
    func sendAnswer(id: String, answer: String) {
        let message: [String: String] = ["type": "answer", "id": id, "answer": answer]
        guard var data = try? JSONSerialization.data(withJSONObject: message) else { return }
        data.append(0x0A)
        lock.lock(); defer { lock.unlock() }
        guard fd >= 0 else { log("no agent connected; answer not sent"); return }
        data.withUnsafeBytes { _ = write(fd, $0.baseAddress, data.count) }
    }

    private func connectToAgent() -> Int32? {
        let socketFD = socket(AF_UNIX, SOCK_STREAM, 0)
        guard socketFD >= 0 else { return nil }
        var address = sockaddr_un()
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        address.sun_family = sa_family_t(AF_UNIX)
        let capacity = MemoryLayout.size(ofValue: address.sun_path)
        guard path.utf8.count < capacity else { close(socketFD); return nil }
        withUnsafeMutableBytes(of: &address.sun_path) { buffer in
            for (index, byte) in path.utf8.enumerated() { buffer[index] = byte }
        }
        let result = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(socketFD, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        if result != 0 {
            if !reportedFailure { reportedFailure = true; log("cannot reach the agent at \(path): \(String(cString: strerror(errno))) (retrying quietly)") }
            close(socketFD)
            return nil
        }
        reportedFailure = false
        return socketFD
    }

    private func readEvents(from socketFD: Int32) {
        var pending = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = read(socketFD, &buffer, buffer.count)
            if count <= 0 { return }
            pending.append(buffer, count: count)
            while let newline = pending.firstIndex(of: 0x0A) {
                let line = pending.prefix(upTo: newline)
                pending.removeSubrange(...newline)
                handle(Data(line))
            }
        }
    }

    private func handle(_ line: Data) {
        guard let object = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
              let type = object["type"] as? String else {
            log("ignoring malformed event")
            return
        }
        switch type {
        case "state":
            if let name = object["state"] as? String, let state = AshState(rawValue: name),
               [.idle, .listening, .thinking, .speaking].contains(state) {
                model.apply(state)
            }
        case "reply":
            model.apply(.reply, text: object["text"] as? String ?? "")
        case "crew":
            model.apply(.crew, text: object["message"] as? String ?? "")
        case "confirm":
            if let id = object["id"] as? String {
                model.apply(.confirm, text: object["question"] as? String ?? "", confirmID: id)
            }
        case "confirm_closed":
            model.apply(.idle, immediate: true)
        case "error":
            model.apply(.reply, text: "Error: " + (object["message"] as? String ?? "something broke"))
        case "heard":
            log("heard: \(object["text"] as? String ?? "")")
        default:
            log("ignoring unknown event type \(type)")
        }
    }
}
