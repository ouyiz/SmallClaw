from fastapi import FastAPI

# 步骤1：导入 FastAPI 类
# 步骤2：创建应用实例
app = FastAPI()

# 步骤3：定义路径操作装饰器
# 步骤4：定义路径操作函数
@app.get("/")
async def root():
    # 步骤5：返回响应内容
    return {"message": "Hello World"}