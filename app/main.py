from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from mangum import Mangum
from app.auth import create_access_token, verify_token, ACCESS_TOKEN_EXPIRE_MINUTES
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import aioboto3
from boto3.dynamodb.types import TypeDeserializer
import os
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
if os.path.exists('.env'):
    from dotenv import load_dotenv
    load_dotenv()
    
API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
app = FastAPI(
    title="JTA Residential Healthcare API",
    version="1.0.0",
    description="""
    The JTA Residential Healthcare API provides a comprehensive suite of endpoints to manage staff and expenses within the residential healthcare setting. This API is designed to streamline the administrative tasks associated with managing staff records, tracking expenses, and ensuring compliance with healthcare standards.
    
    ## Features
    
    - **Staff Management**: Create, update, and retrieve staff information.
    - **Expense Tracking**: Record and manage various expenses including maintenance, IT, and general expenses.
    - **Shift Management**: Log and manage staff shifts, including start and end times, overtime, and total hours worked.
    
    This API aims to provide a seamless integration for managing residential healthcare operations, improving efficiency, and reducing administrative overhead.
    """,
    summary="API for managing staff, expenses, and shifts in JTA Residential Healthcare",
    contact={
        "name": "JTA Support",
        "url": "https://www.jtahealthcare.com/support",
        "email": "support@jtahealthcare.com",
    },
    terms_of_service="https://www.jtahealthcare.com/terms",
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },)


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

session = aioboto3.Session(
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_DEFAULT_REGION', 'eu-north-1')
)
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Helper function to deserialize DynamoDB items
def deserialize_dynamodb_item_for_list(item):
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in item.items()}
# def deserialize_dynamodb_item(item):
#     """Convert DynamoDB item to a regular Python dictionary"""
#     deserialized_item = {}
#     for key, value in item.items():
#         data_type = list(value.keys())[0]
#         deserialized_item[key] = value[data_type]
#     return deserialized_item

# Helper function for deserializing DynamoDB items - Update Route
def deserialize_dynamodb_item(item):
    if 'S' in item:
        return item['S']
    elif 'N' in item:
        return float(item['N']) if '.' in item['N'] else int(item['N'])
    else:
        raise ValueError("Unsupported DynamoDB data type")
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Pydantic models for Staff and Shift
class Staff(BaseModel):
    staffID: str
    fullName: str
    employmentType: str
    jobTitle: str
    hourlyRate: float

class Shift(BaseModel):
    staffID: str
    startDate: str
    endDate: str
    house: str
    shift: str
    shiftStart: str
    shiftEnd: str
    overtime: float
    totalHours: float
    totalWage: float
    absence: str
    absenceStatus: str
    
class Expense(BaseModel):
    expenseID: str
    date: str
    youngPersonWeeklyMoney: float
    maintenance: float
    IT: float
    misc: float
    pettyCash: float
    general: float
    
class UpdateStaffRequest(BaseModel):
    updates: Dict[str, str]
    
class Token(BaseModel):
    access_token: str
    token_type: str
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  GENERAL VIEW  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
@app.get("/", tags=["General View"])
async def root():
    return {"message": "Welcome to JTA Residential Care API"}

# -----------------------------------------------------------------------------------------------------------
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  LOGIN ROUTE  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
@app.post("/token", response_model=Token, tags=["Login"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    
    if form_data.username != API_USERNAME or form_data.password != API_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# -----------------------------------------------------------------------------------------------------------
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  STAFF MANAGEMENT  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
@app.post("/jta/api/staff", tags=["Create Staff"])
async def create_staff(staff: Staff, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            item = {
                'staffID': {'S': staff.staffID},
                'fullName': {'S': staff.fullName},
                'employmentType': {'S': staff.employmentType},
                'jobTitle': {'S': staff.jobTitle},
                'hourlyRate': {'N': str(staff.hourlyRate)}
            }
            await client.put_item(TableName='Staff', Item=item)
        return {"message": "Staff created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# -----------------------------------------------------------------------------------------------------------
@app.get("/jta/api/staff", response_model=List[dict], tags=["List all staffs"])
async def get_all_staff(token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            response = await client.scan(TableName='Staff')
            items = response.get('Items', [])
            deserialized_items = [deserialize_dynamodb_item_for_list(item) for item in items]
            return deserialized_items if deserialized_items else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    
# -----------------------------------------------------------------------------------------------------------

@app.get("/jta/api/staff/{staff_id}", response_model=dict, tags=["Gets a staff"])
async def get_staff(staff_id: str, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            response = await client.get_item(TableName='Staff', Key={'staffID': {'S': staff_id}})
            item = response.get('Item', None)
            return deserialize_dynamodb_item(item) if item else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  
# -----------------------------------------------------------------------------------------------------------
@app.put("/jta/api/staff/{staff_id}", response_model=dict, tags=["Updates a staff"] )
async def update_staff(staff_id: str, request: UpdateStaffRequest, token: str = Depends(verify_token)):
    try:
        updates = request.updates  # Access the updates attribute from the request
        # Ensure the input is a dictionary
        if not isinstance(updates, dict):
            raise ValueError("Updates should be provided as a dictionary")
        
        # Construct the update expression
        update_expression = "SET " + ", ".join(f"{k} = :{k}" for k in updates.keys())
        expression_attribute_values = {f":{k}": v for k, v in updates.items()}
        
        # Get the DynamoDB table client
        async with session.client('dynamodb') as client:
            update_expression = "SET " + ", ".join(f"{k} = :{k}" for k in updates.keys())
            expression_attribute_values = {f":{k}": {'S': v} if isinstance(v, str) else {'N': str(v)} for k, v in updates.items()}
        
        # Get the DynamoDB table client,
        
        # Update the item in the table
        response = await client.update_item(
            TableName='Staff',
            Key={'staffID': {'S': staff_id}},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        # Get the updated attributes
        attributes = response.get('Attributes', None)
        
        # Deserialize the attributes if they exist
        return {k: deserialize_dynamodb_item(v) for k, v in attributes.items()} if attributes else {}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# -----------------------------------------------------------------------------------------------------------
@app.delete("/jta/api/staff/{staff_id}", response_model=dict, tags=["Deletes a staff"])
async def delete_staff(staff_id: str, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            await client.delete_item(TableName='Staff', Key={'staffID': {'S': staff_id}})
        return {"message": "Staff deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# -----------------------------------------------------------------------------------------------------------

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  SHIFTS MANAGEMENT  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

@app.get("/jta/api/shifts", response_model=List[dict], tags=["Lists all shifts"])
async def get_all_shifts(token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            response = await client.scan(TableName='Shifts')
            items = response.get('Items', [])
            deserialized_items = [deserialize_dynamodb_item_for_list(item) for item in items]
            return deserialized_items if deserialized_items else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------------------------------------

@app.get("/jta/api/shifts/{shift_id}/{start_date}", response_model=dict, tags=["Gets a shift for a particular date"])
async def get_shift(staff_id: str, start_date: str, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            response = await client.get_item(TableName='Shifts', Key={'shiftID': {'S': 'shift_id'}, 'startDate': {'S': start_date}})
            item = response.get('Item', None)
            return deserialize_dynamodb_item(item) if item else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------------------------------------

@app.put("/jta/api/shifts/{shift_id}/{start_date}", response_model=dict, tags=["Updates a shift for a particular date"] )
async def update_shift(staff_id: str, start_date: str, request: UpdateStaffRequest, token: str = Depends(verify_token)):
    try:
        updates = request.updates  # Access the updates attribute from the request
        # Ensure the input is a dictionary
        if not isinstance(updates, dict):
            raise ValueError("Updates should be provided as a dictionary")
        
        # Construct the update expression
        update_expression = "SET " + ", ".join(f"{k} = :{k}" for k in updates.keys())
        expression_attribute_values = {f":{k}": v for k, v in updates.items()}
        
        # Get the DynamoDB table client
        async with session.client('dynamodb') as client:
            update_expression = "SET " + ", ".join(f"{k} = :{k}" for k in updates.keys())
            expression_attribute_values = {f":{k}": {'S': v} if isinstance(v, str) else {'N': str(v)} for k, v in updates.items()}
            response = await client.update_item(
                TableName='Shifts',
                Key={'shiftID': {'S': 'shift_id'}, 'startDate': {'S': start_date}},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="UPDATED_NEW"
            )
            attributes = response.get('Attributes', None)
            return {k: deserialize_dynamodb_item(v) for k, v in attributes.items()} if attributes else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------------------------------------

@app.post("/jta/api/shifts", tags=["Create Shift"])
async def create_shift(shift: Shift, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            item = {
                'staffID': {'S': shift.staffID},
                'startDate': {'S': shift.startDate},
                'endDate': {'S': shift.endDate},
                'house': {'S': shift.house},
                'shift': {'S': shift.shift},
                'shiftStart': {'S': shift.shiftStart},
                'shiftEnd': {'S': shift.shiftEnd},
                'overtime': {'N': str(shift.overtime)},
                'totalHours': {'N': str(shift.totalHours)},
                'totalWage': {'N': str(shift.totalWage)},
                'absence': {'S': str(shift.absence)},
                'absenceStatus': {'S': str(shift.absenceStatus)}
                }
        await client.put_item(TableName='Shifts', Item=item)
        return {"message": "Shift created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------------------------------------

@app.delete("/jta/api/shifts/{shift_id}/{start_date}", response_model=dict, tags=["Deletes a shift for a particular date"])
async def delete_shift(staff_id: str, start_date: str, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            await client.delete_item(TableName='Shifts', Key={'shiftID': {'S': 'shift_id'}, 'startDate': {'S': start_date}})
        return {"message": "Shift deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------------------------------------

@app.post("/jta/api/expense", tags=["Create expense"])
async def create_expense(expense: Expense, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            item = {
        'expenseID': {'S': expense.expenseID},
        'date': {'S': expense.date},
        'youngPersonWeeklyMoney': {'N': str(expense.youngPersonWeeklyMoney)},
        'maintenance': {'N': str(expense.maintenance)},
        'IT': {'N': str(expense.IT)},
        'misc': {'N': str(expense.misc)},
        'pettyCash': {'N': str(expense.pettyCash)},
        'general': {'N': str(expense.general)}
    }
            await client.put_item(TableName='Expenses', Item=item)
        return {"message": "Expense created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# -----------------------------------------------------------------------------------------------------------

@app.get("/jta/api/expenses", response_model=List[dict], tags=["List all expenses"])
async def get_all_expenses(token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            response = await client.scan(TableName='Expenses')
            items = response.get('Items', [])
            deserialized_items = [deserialize_dynamodb_item_for_list(item) for item in items]
            return deserialized_items if deserialized_items else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# -----------------------------------------------------------------------------------------------------------

@app.get("/jta/api/expense/{expense_id}/{date}", response_model=dict, tags=["Get expense by date and ID"])
async def get_expense(expense_id: str, date: str, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            response = await client.get_item(TableName='Expenses', Key={'expenseID': {'S': expense_id}, 'date': {'S': date}})
            item = response.get('Item', None)
            return deserialize_dynamodb_item(item) if item else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------------------------------------

@app.put("/jta/api/expense/{expense_id}/{date}", response_model=dict, tags=["Updates expense for a specific date"] )
async def update_expense(expense_id: str, date: str, request: UpdateStaffRequest, token: str = Depends(verify_token)):
    try:
        updates = request.updates  # Access the updates attribute from the request
        # Ensure the input is a dictionary
        if not isinstance(updates, dict):
            raise ValueError("Updates should be provided as a dictionary")
        
        # Construct the update expression
        update_expression = "SET " + ", ".join(f"{k} = :{k}" for k in updates.keys())
        expression_attribute_values = {f":{k}": v for k, v in updates.items()}
        
        # Get the DynamoDB table client
        async with session.client('dynamodb') as client:
            update_expression = "SET " + ", ".join(f"{k} = :{k}" for k in updates.keys())
            expression_attribute_values = {f":{k}": {'S': v} if isinstance(v, str) else {'N': str(v)} for k, v in updates.items()}
            response = await client.update_item(
                TableName='Expenses',
                Key={'expenseID': {'S': expense_id}, 'date': {'S': date}},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="UPDATED_NEW"
            )
            attributes = response.get('Attributes', None)
            return {k: deserialize_dynamodb_item(v) for k, v in attributes.items()} if attributes else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------------------------------------

@app.delete("/jta/api/expense/{expense_id}/{date}", response_model=dict, tags=["Deletes expense for a particular date"])
async def delete_expense(expense_id: str, date: str, token: str = Depends(verify_token)):
    try:
        async with session.client('dynamodb') as client:
            await client.delete_item(TableName='Expenses', Key={'expenseID': {'S': expense_id}, 'date': {'S': date}})
        return {"message": "Expense deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



