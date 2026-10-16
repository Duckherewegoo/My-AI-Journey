// webpack.config.js
const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');

module.exports = {
  mode: 'development',
  entry: './ct-sr/script/index.js',
  output: {
    filename: 'bundle.js',
    path: path.resolve(__dirname, 'ct-sr'),
    publicPath: '/'
  },
  devServer: {
    static: {
      directory: path.join(__dirname, 'ct-sr'),
    },
    compress: true,
    port: ,
    hot: true,
    open: true,
    historyApiFallback: true
  },
  module: {
    rules: [
      // 新增：处理 .js 文件，用 babel-loader 转译 ES 新语法（核心添加）
      {
        test: /\.js$/, // 匹配所有 .js 文件
        exclude: /node_modules/, // 排除 node_modules 目录，不转译第三方包
        use: {
          loader: 'babel-loader' // 使用 babel-loader 处理
        }
      },
      // 你的原有 Less 规则（保持不变，无需修改）
      {
        test: /\.less$/,
        use: [
          'style-loader',
          'css-loader',
          {
            loader: 'less-loader',
            options: {
              lessOptions: {
                strictMath: true,
              },
            },
          },
        ],
      }
    ]
  },
  externals: {
    // 暴露全局变量，让 Webpack 不打包，直接使用 window 上的对象
    cornerstone: 'cornerstone',
    cornerstoneWebImageLoader: 'cornerstoneWebImageLoader',
    dicomParser: 'dicomParser'
  },
  plugins: [
    new HtmlWebpackPlugin({
      template: './ct-sr/index.html',
      filename: 'index.html',
      inject: 'body'
    })
  ],
  resolve: {
    extensions: ['.js', '.less']
  }
};

