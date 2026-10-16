<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CT图像深度学习超分辨率平台</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
        }

        body {
            background-color: #f5f7fa;
            color: #333;
            line-height: 1.5;
        }

        .banner {
            background-color: #ffffff;
            padding: 1.5rem 0;
            text-align: center;
            border-bottom: 1px solid #eef2f5;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .banner h1 {
            font-size: 2rem;
            font-weight: 500;
            color: #1a2b48;
            margin-bottom: 0.5rem;
        }

        .banner p {
            font-size: 1.05rem;
            color: #607d8b;
        }

        .container {
            max-width: 1200px;
            margin: 3rem auto;
            padding: 0 1rem;
            display: flex;
            gap: 2.5rem;
            flex-wrap: wrap;
        }

        .left {
            flex: 1;
            min-width: 512px;
        }

        #image-display {
            width: 100%;
            height: 512px;
            background-color: #ffffff;
            border: 1px solid #eef2f5;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            overflow: hidden;
            transition: box-shadow 0.2s ease;
        }

        #image-display:hover {
            box-shadow: 0 6px 16px rgba(0,0,0,0.07);
        }

        .right {
            flex: 0 0 420px;
            background-color: #ffffff;
            padding: 2rem;
            border-radius: 8px;
            border: 1px solid #eef2f5;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            transition: box-shadow 0.2s ease;
        }

        .right:hover {
            box-shadow: 0 6px 16px rgba(0,0,0,0.07);
        }

        .right-title {
            font-size: 1.3rem;
            font-weight: 500;
            color: #1a2b48;
            margin-bottom: 1.8rem;
            padding-bottom: 0.8rem;
            border-bottom: 1px solid #eef2f5;
        }

        .section {
            margin-bottom: 2rem;
        }

        .section p {
            color: #546e7a;
            margin-bottom: 1rem;
        }

        #info-display {
            list-style: none;
            color: #546e7a;
            line-height: 2;
            width: 100%;
        }

        #info-display li {
            display: flex;
            justify-content: space-between;
            align-items: center;
            word-break: break-all;
        }

        #info-display li span {
            color: #90a4ae;
            flex-shrink: 0;
            margin-left: 10px;
            text-align: right;
            width: 200px;
        }

        select, input[type="number"] {
            padding: 0.6rem 0.9rem;
            border: 1px solid #eef2f5;
            border-radius: 6px;
            font-size: 0.95rem;
            color: #546e7a;
            background-color: #ffffff;
            margin-right: 0.8rem;
            margin-bottom: 1rem;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
            -moz-appearance: none;
            -webkit-appearance: none;
            appearance: none;
            background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='6'%3E%3Cpath fill='%23546e7a' d='M0 0l6 6 6-6z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 0.9rem center;
            background-size: 12px 6px;
            padding-right: 2.5rem;
        }

        input[type="file"] {
            padding: 0.8rem 0.9rem;
            border: 1px dashed #cfd8dc;
            border-radius: 6px;
            font-size: 0.95rem;
            color: #546e7a;
            background-color: #fafbfc;
            margin-bottom: 1rem;
            cursor: pointer;
            transition: border-color 0.2s ease, background-color 0.2s ease;
            width: 100%;
        }

        select:focus, input[type="number"]:focus, input[type="file"]:focus {
            outline: none;
            border-color: #2196f3;
            box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.1);
        }

        input[type="number"] {
            width: 100px;
        }

        input[type="file"]:hover {
            border-color: #2196f3;
            background-color: #f5f9ff;
        }

        .btn {
            padding: 0.6rem 1.2rem;
            border: none;
            border-radius: 6px;
            background-color: #2196f3 !important;
            color: #ffffff !important;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-right: 0.8rem;
            margin-bottom: 1rem;
            -moz-user-select: none;
            -webkit-user-select: none;
            user-select: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        .btn:hover {
            background-color: #1976d2 !important;
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(25, 118, 210, 0.3);
        }

        .btn:active {
            background-color: #1565c0 !important;
            transform: translateY(0);
            box-shadow: none;
        }

        #sr-area {
            margin-top: 1.2rem;
            width: 100%;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
        }

        #sr-loading, #sr-done {
            margin-left: 0.8rem;
            color: #78909c;
            vertical-align: middle;
            margin-bottom: 1rem;
        }

        #sr-done {
            color: #2e7d32;
            font-weight: 500;
        }

        .operation-group {
            margin-bottom: 1rem;
            width: 100%;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
        }

        .operation-label {
            margin-right: 0.8rem;
            color: #546e7a;
            flex-shrink: 0;
            margin-bottom: 0.5rem;
        }

        .zoom-info {
            margin-right: 1rem;
            color: #546e7a;
            margin-bottom: 0.5rem;
        }

        @media (max-width: 900px) {
            .container {
                flex-direction: column;
                margin: 2rem auto;
                gap: 2rem;
            }

            .left {
                min-width: 100%;
            }

            .right {
                width: 100%;
                max-width: 100%;
                flex: none;
            }
        }

        @-moz-document url-prefix() {
            .btn {
                background-color: #2196f3;
                border: none;
            }

            select {
                background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='6'%3E%3Cpath fill='%23546e7a' d='M0 0l6 6 6-6z'/%3E%3C/svg%3E");
            }
        }
    </style>
</head>
<body>
    <div class="banner">
        <h1>CT图像深度学习超分辨率系统</h1>
        <p>by 姜传奇</p>
    </div>
    <div class="container">
        <div class="left">
            <div
                id="image-display"
                oncontextmenu="return false"
                onmousedown="return false"
            ></div>
        </div>
        <div class="right">
            <p class="right-title">控制面板</p>
            <div class="section">
                <p>
                    远端推理服务状态：<span id="remote-ip">N/A</span>&nbsp;<span
                        id="remote-status"
                        >N/A</span
                    >
                </p>
            </div>
            <div class="section">
                <span>当前DICOM文件</span>
                <input type="file" id="openDicom" accept=".dcm" />
            </div>
            <div class="section">
                <span>当前图像信息</span>
                <br />
                <ul id="info-display">
                    <li>文件名：<span id="info-filename">N/A</span></li>
                    <li>类型：<span id="info-type">N/A</span></li>
                    <li>高H：<span id="info-h">N/A</span></li>
                    <li>宽W：<span id="info-w">N/A</span></li>
                    <li>传输语义：<span id="info-transfer">N/A</span></li>
                </ul>
            </div>
            <div class="section">
                <span>功能操作区</span>
                <br /><br />
                <div class="operation-group">
                    <span class="operation-label">窗预设：</span>
                    <select name="presetWWWL" id="presetWWWL"></select>
                    <label class="operation-label">窗宽WW</label>
                    <input id="ww-input" type="number" value="256" />
                    <label class="operation-label">窗位WL</label>
                    <input id="wl-input" type="number" value="128" />
                    <button id="apply-btn" class="btn">应用</button>
                </div>
                <div class="operation-group">
                    <span class="zoom-info">当前放大倍率：<span id="current-zoom-rate">1.00</span>×</span>
                    <button id="zoomIn-btn" class="btn">放大</button>
                    <button id="zoomOut-btn" class="btn">缩小</button>
                </div>
                <div class="operation-group">
                    <button id="invert-btn" class="btn">反相</button>
                    <button id="reset-btn" class="btn">重设</button>
                </div>
                <div id="sr-area">
                    <button id="sr-btn" class="btn">超分辨率</button>
                    <div id="sr-loading">
                        <span>后台处理中…</span>
                    </div>
                    <div id="sr-done">
                        <span>√ 已完成</span>
                        <button id="sr-replace" class="btn">立即替换</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        window._ctsr = {}
    </script>
    <script src="./lib/cornerstone.js"></script>
    <script src="./lib/cornerstoneMath.min.js"></script>
    <script src="./lib/cornerstoneTools.min.js"></script>
    <script src="./lib/dicomParser.min.js"></script>
    <script src="./lib/cornerstoneWebImageLoader.js"></script>
    <script src="./lib/cornerstoneWADOImageLoader.js"></script>
    <script src="./lib/dicomTransferUids.js"></script>
    <script src="./bundle.js"></script>
</body>
</html>
