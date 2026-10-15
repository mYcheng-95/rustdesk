//! 自建更新通道手动集成测试（真实网络，不进常规测试集）。
//!
//! 运行方式：cargo test --test update_check_manual -- --ignored --nocapture
//!
//! 覆盖三条路径（对应与软件发布平台的契约定稿）：
//! 1. mock 端点返回更高版本（9.9.9）→ 触发：SOFTWARE_UPDATE_URL 被写入响应 url；
//! 2. 真实平台端点（版本与本地相等）→ 不触发：SOFTWARE_UPDATE_URL 保持空；
//! 3. mock 端点返回 404+空 body → 容错：do_check 返回 Err（生产代码中由
//!    allow_err! 静默吞掉，UI 无提示）。
//!
//! 全局状态说明：本测试会临时修改 APP_NAME 与 update-api-url option，
//! 结束后恢复；update-api-url 写入的是本机配置文件（%APPDATA%），
//! 测试末尾清空还原。

use std::io::{Read, Write};

fn spawn_mock(responses: Vec<(u16, String)>) -> u16 {
    // 127.0.0.1:0 由系统分配空闲端口，避免测试间端口冲突
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    std::thread::spawn(move || {
        for (status, body) in responses {
            let (mut stream, _) = listener.accept().unwrap();
            // 粗读一次请求（header+body 合并缓冲）即可回写响应；
            // Connection: close 让 reqwest 单请求单连接，无需解析请求内容
            let mut buf = [0u8; 16384];
            let _ = stream.read(&mut buf);
            let status_text = match status {
                200 => "OK",
                404 => "Not Found",
                _ => "Status",
            };
            let resp = format!(
                "HTTP/1.1 {} {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                status, status_text, body.len(), body
            );
            stream.write_all(resp.as_bytes()).unwrap();
        }
    });
    port
}

#[test]
#[ignore] // 真实网络依赖（127.0.0.1 mock + 平台线上端点），仅手动运行
fn update_check_full_chain() {
    // 模拟品牌构建：is_custom_client() 依赖运行时 APP_NAME
    {
        let mut name = hbb_common::config::APP_NAME.write().unwrap();
        *name = "TaDesk".to_owned();
    }

    // ---- 路径 1：mock 端点返回 9.9.9 → 触发 ----
    let port = spawn_mock(vec![(
        200,
        r#"{"url":"http://127.0.0.1:1/tags/9.9.9","download_url":"http://example.com/dl"}"#.to_string(),
    )]);
    hbb_common::config::Config::set_option(
        "update-api-url".to_string(),
        format!("http://127.0.0.1:{}/tags/latest", port),
    );
    librustdesk::common::do_check_software_update().expect("mock 检查应成功");
    let got = librustdesk::common::SOFTWARE_UPDATE_URL.lock().unwrap().clone();
    assert_eq!(got, "http://127.0.0.1:1/tags/9.9.9", "9.9.9 > 本地版本应触发并写入响应 url");
    println!("[1/3] mock 触发路径 OK: {}", got);

    // ---- 路径 2：真实平台端点（线上 1.5.1 == 本地 1.5.1）→ 不触发 ----
    hbb_common::config::Config::set_option(
        "update-api-url".to_string(),
        "http://tasoft.ataoptics.com:38088/api/v1/rustdesk/tadesk/stable/tags/latest".to_string(),
    );
    librustdesk::common::do_check_software_update().expect("平台检查应成功");
    let got = librustdesk::common::SOFTWARE_UPDATE_URL.lock().unwrap().clone();
    assert!(got.is_empty(), "版本相等不应触发，SOFTWARE_UPDATE_URL 应为空，实际: {}", got);
    println!("[2/3] 平台端点等版本不触发 OK（响应契约与网络链路真实可达）");

    // ---- 路径 3：404+空 body → Err（生产中静默容错）----
    let port = spawn_mock(vec![(404, String::new())]);
    hbb_common::config::Config::set_option(
        "update-api-url".to_string(),
        format!("http://127.0.0.1:{}/tags/latest", port),
    );
    let res = librustdesk::common::do_check_software_update();
    assert!(res.is_err(), "404 空 body 应返回 Err（生产由 allow_err! 静默）");
    println!("[3/4] 404 静默容错路径 OK");

    // ---- 路径 4：download_url 三层解析——option 覆盖平台响应 ----
    // 背景：平台响应的 download_url 落地页路由 404，由 option（心跳下发/
    // 本地手改）或编译期注入覆盖修正；此处验证 option 层优先于响应值。
    let port = spawn_mock(vec![(
        200,
        r#"{"url":"http://127.0.0.1:1/tags/9.9.9","download_url":"http://bad.example/404page"}"#.to_string(),
    )]);
    hbb_common::config::Config::set_option(
        "update-api-url".to_string(),
        format!("http://127.0.0.1:{}/tags/latest", port),
    );
    hbb_common::config::Config::set_option(
        "update-download-url".to_string(),
        "http://tasoft.ataoptics.com:38088/portal/software/TaDesk".to_string(),
    );
    librustdesk::common::do_check_software_update().expect("mock 检查应成功");
    let dl = librustdesk::common::SOFTWARE_UPDATE_DOWNLOAD_URL
        .lock()
        .unwrap()
        .clone();
    assert_eq!(
        dl, "http://tasoft.ataoptics.com:38088/portal/software/TaDesk",
        "option 覆盖应优先于平台响应的 download_url，实际: {}",
        dl
    );
    println!("[4/4] download_url option 覆盖路径 OK: {}", dl);

    // ---- 恢复全局状态，避免污染本机配置 ----
    hbb_common::config::Config::set_option("update-api-url".to_string(), "".to_string());
    hbb_common::config::Config::set_option("update-download-url".to_string(), "".to_string());
    {
        let mut name = hbb_common::config::APP_NAME.write().unwrap();
        *name = "RustDesk".to_owned();
    }
    *librustdesk::common::SOFTWARE_UPDATE_URL.lock().unwrap() = "".to_string();
}
