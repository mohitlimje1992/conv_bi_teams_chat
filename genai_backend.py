import numpy as np
import pandas as pd
import re
import json
import plotly.graph_objects as go
import copy
import plotly.express as px
from sqlalchemy import create_engine
import urllib.parse
import pyodbc
import os
from openai import AzureOpenAI
# driver = "SQL Server" # vs code (local)
driver = "ODBC Driver 17 for SQL Server"  # github(deployment)

# jdbc:sqlserver://mobility-coe-db-server.database.windows.net:1433;database=mobility-coe-db;user=admin-user@mobility-coe-db-server;password={your_password_here};encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;loginTimeout=30;
server = 'exl-rmti-training-app-server.database.windows.net:1433'
database = 'exl-rmti-training-app'
username = 'exl-rmti-admin'
password = 'training@123'
# conn = pyodbc.connect('Driver={SQL Server};Server='+server+  ';UID='+username+';PWD='+password+';Database='+database)
connection_string = 'Driver={ODBC Driver 17 for SQL Server};Server=tcp:exl-rmti-training-app-server.database.windows.net,1433;Database=exl-rmti-training-app;Uid=exl-rmti-admin;Pwd=training@123;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
conn = pyodbc.connect(connection_string)
# connection_string = "Driver={ODBC Driver 18 for SQL Server};Server=tcp:harmony-db.database.windows.net,1433;Database=GPT;Uid=harmony;Pwd=Comcast@2024;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
os.environ["OPENAI_API_TYPE"] = "azure"
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://genaiinitiativeopenai.openai.azure.com/"
os.environ["OPENAI_API_KEY"] = "cd2823e85ca04aafa6d7bd0c8cce22d1"
os.environ["OPENAI_API_VERSION"] = "2024-12-01-preview"


client = AzureOpenAI(
azure_endpoint = "https://genaiinitiativeopenai.openai.azure.com/", 
api_key="cd2823e85ca04aafa6d7bd0c8cce22d1",  
api_version="2024-08-01-preview")


# from trino.dbapi import connect
# from trino.auth import BasicAuthentication
# conn = connect(
#     http_scheme="https",
#     host="query.comcast.com",
#     port=8443,
#     user="ukonth238",
#     auth=BasicAuthentication("ukonth238", "Philly18@Philly18@")
# )




# table_dict = {"minio.dx_dl_comcast_cbmarketing.production_demands_sales_table_0225":"minio.dx_dl_comcast_cbmarketing.production_demands_sales_table_0225"}
table_dict = {"dbo.product": "dbo.product","dbo.orders_data":"dbo.orders_data"}
 
def send_gpt_request(
    client,
    prompt,
    max_tokens=1000,
    temperature=0.1,
    top_p=1,
    max_retries=5,):

    message_text = [{"role":"system","content":prompt}]
    completion = client.chat.completions.create(
    # model="harmony-openai-4o", # model = "deployment_name"
    # model="gpt-35-turbo-16k",
    model ='Azure-Open-AI-Deployment',
    messages = message_text,
    temperature=temperature,
    max_tokens=max_tokens,
    top_p=top_p,
    frequency_penalty=0,
    presence_penalty=0,
    stop=None)

    return completion



def run_bq_sql(query_string, table_dict):
   
    rep_dict = table_dict
    for key, value in rep_dict.items():
        query_string = query_string.replace(key, value)

    print("----------------run_bq_sql query-------------",query_string)
    #df = pd.read_sql_query(query_string, create_engine(connection_string))
    cur = conn.cursor()
    cur.execute(query_string)
    rows = cur.fetchall()
    print(len(rows))  # Number of rows
    print(len(rows[0]))

    columns = [desc[0] for desc in cur.description]
    
    frame = {column: [] for column in columns}

    # Iterate through the list of tuples and append the elements to the corresponding lists
    for i in range(len(rows)):
        for j, column in enumerate(columns):
            frame[column].append(rows[i][j])

    # Show the frame (dictionary of lists for each column)
    df=pd.DataFrame(frame)
    print(df)
        
    return df


def get_table_output(llm_response, table_dict):
    SQL_query = (
        llm_response.replace("Query:", "")
        .replace("```", "")
        .replace("SQL", "")
        .replace("sql", "").replace('"""', "")
    )
   
    check_success = False
    try_no = 1
    max_try = 2
    while not check_success and try_no <= max_try:
        try:
            df_table = run_bq_sql(SQL_query, table_dict)
            check_success = True
          
        except Exception as e:
            print("-------------Exception-----------------------",e)
            try_no += 1
            try:
                correct_sql_prompt = f"""Here is the response from LLM: {SQL_query}. First figure out if there is any SQL Query in LLM response. If not just say "I don't know.". If it contains an incorrect SQL Query follow the below steps:
                wrong Microsoft SQL: {SQL_query} , \n
                error: {e} , \n
                Output: Just Corrected SQL query only, Please do not include any comments or non-SQL keywords or definition"""
                SQL_query = (send_gpt_request(client, correct_sql_prompt)).choices[0].message.content.replace("Query:", "").replace("```", "").replace("sql", "").replace("SQL", "").replace('"""', "")

                if SQL_query == "I don't know." or SQL_query.startswith("I'm sorry"):
                    return pd.DataFrame(), None
                df_table = run_bq_sql(SQL_query, table_dict)
                check_success = True
               
            except Exception as e2:
                if 'Divide by zero error encountered' in str(e2) and try_no==max_try:
                    
                    return pd.DataFrame({'Messages': 'Divide by zero error encountered'}, index=[0]), SQL_query
                elif 'COLUMN_NOT_FOUND' and try_no==max_try:
                    return pd.DataFrame({'Messages': 'One of the column is not found in dataset'}, index=[0]), SQL_query
                else:
                    pass
                
    if df_table.shape[0]==0 and df_table.shape[1] >= 1:
        return pd.DataFrame({'Messages': 'Query might succeeded, Affected rows: 0'}, index=[0]), SQL_query
    elif check_success == False:
        return pd.DataFrame({'Messages': 'Other data error encountered'}, index=[0]), SQL_query

    return df_table, SQL_query


####################################### SQL Summary ##################################


def get_sql_query_summary(SQL_query):

    SQL_Query1= """SELECT top 10 fiscal_month as "Fiscal Month",
    Campaign_Name as "Campaign Name", 
        round((SUM(emails_open) / NULLIF(SUM(emails_delivered),0))*100,2) AS "Open Rate%"
    FROM email_campaign_backend
    WHERE fiscal_month = '2024-07-01' 
    AND Audience = 'SMB' AND (campaign_name LIKE '%Marriott%' OR parent_campaign LIKE '%Marriott%') AND KPI IN ('Call_Leads', 'Web_Leads', 'Chat_Leads', 'OFT_Leads')
    GROUP BY Campaign_Name,fiscal_month having SUM(emails_delivered) >=1000
    ORDER BY "Open Rate%" DESC"""

    SQL_Query2="""

    WITH CompetitorConnects AS
      (SELECT xm_act.region_name AS region,
              aci.top1_speed_competitor_name AS top_speed_competitor,
              COALESCE(SUM(CASE WHEN (xm_act.line_activity_name = 'CONNECT') AND ((xm_act.line_activity_type<> 'XM MV') OR (xm_act.line_activity_type IS NULL)) THEN xm_act.xm_ind  ELSE NULL END), 0) as [XM Connects(Lines)]
              FROM nsd_combined_xm_activity_dv AS xm_act
       INNER JOIN address_competitive_intelligence AS aci ON xm_act.location_id = aci.location_id
       AND xm_act.metric_date BETWEEN aci.record_start_ts AND aci.record_end_ts
       INNER JOIN business_fiscal_calendar AS bfc ON xm_act.metric_date = bfc.cal_dt
       WHERE bfc.fme_dt = '2024-07-21'
       GROUP BY xm_act.region_name,
                aci.top1_speed_competitor_name),
         RankedCompetitors AS
      (SELECT region,top_speed_competitor,[XM Connects(Lines)],
              ROW_NUMBER() OVER (PARTITION BY region ORDER BY [XM Connects(Lines)] DESC) AS rn
       FROM CompetitorConnects)
    SELECT region as Region,
           top_speed_competitor as [Top Speed Competitor],
           [XM Connects(Lines)]
    FROM RankedCompetitors
    WHERE rn = 1
    ORDER BY [XM Connects(Lines)] DESC;
    """

    prompt_template = f"""
    I need your expertise to analyze an SQL query and extract crucial components from it.

    Please provide a detailed breakdown of the following elements:

    Data Assets Utilized: Identify and list all table names referenced in the query.
    Filtering Criteria Applied: Extract the join conditions between the two tables along with join types like INNER, LEFT, FULL OUTER. Extract all applied filters from WHERE and HAVING clause in straightforward language.
   
    Ensure your response is well-organized, with each section distinctly labeled. Your insights will greatly enhance my understanding of this query's structure.
    In WHERE and HAVING conditions make sure you are properly distinguish AND and OR conditions.
    In WHERE and HAVING conditions if there are alias are there then replace it with actual table name.
    If any condition or table name is not specified then just say 'Not Specified'
    Format your response with the same labels as above, without any additional headers or concluding remarks.
    Make sure you are translating technical SQL keyword so that non-technical person can easily understand i.e. DATEADD, DATEDIFF, LIKE, IN, NOT IN...

    following are the example provided for your undestanding:
    first example:
    {SQL_Query1}
    Output:
    Data Assets Utilized: 
    1. email_campaign_backend

    Filtering Criteria Applied:
    1. fiscal_month = '2024-07-01'        
    2. Audience = 'SMB'        
    3. The campaign_name or parent_campaign contains the word 'Marriott'
    4. KPI is one of 'Call_Leads', 'Web_Leads', 'Chat_Leads', 'OFT_Leads'
    5. SUM(emails_delivered) >=1000

    second example:
    {SQL_Query2}
    Output:
    Data Assets Utilized:
    1. nsd_combined_xm_activity_dv
    2. address_competitive_intelligence
    3. business_fiscal_calendar

    Filtering Criteria Applied:
    1. INNER JOIN (Left: nsd_combined_xm_activity_dv, Right: address_competitive_intelligence)
    - Match location_id from left table and right table
    - Ensure metric_date from the left table is within the range of record_start_ts and record_end_ts from the right table
    2. INNER JOIN (Left: nsd_combined_xm_activity_dv, Right: business_fiscal_calendar)
    - Match metric_date from the left table with cal_dt from the right table
    3. fme_dt from business_fiscal_calendar is '2024-07-21'


    Similarly, provide a Tables Name, Join Conditions, WHERE Conditions and HAVING Conditions for the following SQL Query:
    {SQL_query}
    """

    table_where_having = send_gpt_request(client, prompt_template).choices[0].message.content
    return table_where_having


def get_sql_query_summary_direct(SQL_query):

    SQL_Query1= """SELECT top 10 fiscal_month as "Fiscal Month",
    Campaign_Name as "Campaign Name", 
        round((SUM(emails_open) / NULLIF(SUM(emails_delivered),0))*100,2) AS "Open Rate%"
    FROM email_campaign_backend
    WHERE fiscal_month = '2024-07-01' 
    AND Audience = 'SMB' AND Customer_Group = 'Existing Prospect' AND (campaign_name LIKE '%Marriott%' OR parent_campaign LIKE '%Marriott%')
    GROUP BY Campaign_Name,fiscal_month having SUM(emails_delivered) >=1000
    ORDER BY "Open Rate%" DESC"""

    SQL_Query2="""

    WITH CompetitorConnects AS
      (SELECT xm_act.region_name AS region,
              aci.top1_speed_competitor_name AS top_speed_competitor,
              COALESCE(SUM(CASE WHEN (xm_act.line_activity_name = 'CONNECT') AND ((xm_act.line_activity_type<> 'XM MV') OR (xm_act.line_activity_type IS NULL)) THEN xm_act.xm_ind  ELSE NULL END), 0) as [XM Connects(Lines)]
              FROM nsd_combined_xm_activity_dv AS xm_act
       INNER JOIN address_competitive_intelligence AS aci ON xm_act.location_id = aci.location_id
       AND xm_act.metric_date BETWEEN aci.record_start_ts AND aci.record_end_ts
       INNER JOIN business_fiscal_calendar AS bfc ON xm_act.metric_date = bfc.cal_dt
       WHERE bfc.fme_dt = '2024-07-21'
       GROUP BY xm_act.region_name,
                aci.top1_speed_competitor_name),
         RankedCompetitors AS
      (SELECT region,top_speed_competitor,[XM Connects(Lines)],
              ROW_NUMBER() OVER (PARTITION BY region ORDER BY [XM Connects(Lines)] DESC) AS rn
       FROM CompetitorConnects)
    SELECT region as Region,
           top_speed_competitor as [Top Speed Competitor],
           [XM Connects(Lines)]
    FROM RankedCompetitors
    WHERE rn = 1
    ORDER BY [XM Connects(Lines)] DESC;
    """

    prompt_template = f"""
    I need your expertise to analyze an SQL query and extract crucial components from it.

    Please provide a detailed breakdown of the following elements:

    Table Names: Identify and list all table names referenced in the query.
    Join Condition: Extract the join conditions between the two tables along with join types like INNER, LEFT, FULL OUTER.
    WHERE Conditions: Clearly extract and outline all filter conditions specified in the WHERE clause, without repeating any conditions in the ON clause (JOIN Condition).
    HAVING Conditions: Identify and extract any filter conditions specified in the HAVING clause (if applicable).

    Ensure your response is well-organized, with each section distinctly labeled. Your insights will greatly enhance my understanding of this query's structure.
    In WHERE and HAVING conditions make sure you are properly distinguish AND and OR conditions.
    In WHERE and HAVING conditions if there are alias are there then replace it with actual table name.
    If any condition or table name is not specified then just say 'Not Specified'
    Make sure you are not repeatating WHERE and JOIN Conditions
    Format your response with the same labels as above, without any additional headers or concluding remarks.


    following are the example provided for your undestanding:
    first example:
    {SQL_Query1}
    Output:
    Table Names: 
    1. email_campaign_backend

    Join Condition: 
    - Not Specified

    WHERE Conditions: 
    1. fiscal_month = '2024-07-01'        
    2. Audience = 'SMB'        
    3. (campaign_name LIKE '%Marriott%' OR parent_campaign LIKE '%Marriott%')
    4. Customer_Group = 'Existing Prospect'

    HAVING Conditions: 
    1. SUM(emails_delivered) >=1000

    second example:
    {SQL_Query2}
    Output:
    Table Names:
    1. nsd_combined_xm_activity_dv
    2. address_competitive_intelligence
    3. business_fiscal_calendar

    Join Condition:
    1. INNER JOIN address_competitive_intelligence ON nsd_combined_xm_activity_dv.location_id = address_competitive_intelligence.location_id AND nsd_combined_xm_activity_dv.metric_date BETWEEN address_competitive_intelligence.record_start_ts AND address_competitive_intelligence.record_end_ts
    2. INNER JOIN business_fiscal_calendar ON nsd_combined_xm_activity_dv.metric_date = business_fiscal_calendar.cal_dt

    WHERE Conditions:
    1. business_fiscal_calendar.fme_dt = '2024-07-21'

    HAVING Conditions:
    - Not Specified

    Similarly, provide a Tables Name, Join Conditions, WHERE Conditions and HAVING Conditions for the following SQL Query:
    {SQL_query}
    """

    table_where_having = send_gpt_request(client, prompt_template).choices[0].message.content
    return table_where_having

####################################################### GRAPHS ###########################3


def replace_values_in_string(text, args_dict):
    for key in args_dict.keys():
        text = text.replace(key, str(args_dict[key]))
    return text


def remove_null_values(dictt):
    d = {}
    for k, v in dictt.items():
        d[k] = {}
        for k1, v1 in dictt[k].items():
            if v1 != "remove_key":
                d[k][k1] = v1
    return d


def plot_type_prompt_generation(query_prompt: str, df: pd.DataFrame):

    """
    Function to fetch the plot type and corresponding parameters using the sql query and user's query.

    Parameters:
    - query_prompt: User Input

    - sql_query: Query using which can be used to fetch the dataframe

    - db_loc: Location of db file or url
    """

    if df.shape[0] > 1:
        non_unique_col = []
        for col in df:
            if df[col].nunique() != 1:
                non_unique_col += [col]

        df = df[non_unique_col]

    solution_table_columns = list(df.columns)
    print(solution_table_columns)

    graph_list = [
        "Bar Chart",
        "Line Chart",
        "Pie Chart",
        "Scatter Plot",
        "Histogram",
        "Area Chart",
        "Box and Whisker Plot",
        "Heat Map",
        "Bubble Chart",
        "GroupedBar Chart",
        "StackedBar Chart",
    ]

    graph_param_def = f"""
        Potential Parameters for Bar Chart:
        x, y, color = 'z', orientation, facet_row, facet_col
        
        Potential Parameters for GroupedBar Chart:
        x, y, orientation='v'
        
        Potential Parameters for GroupedArea Chart:
        x, y, orientation='v', color=z
        
        Potential Parameters for Line Chart:
        x, y, facet_row, facet_col
        
        Potential Parameters for Pie Chart:
        names, values, facet_row, facet_col
        
        Potential Parameters for Scatter Plot:
        x, y, size, color, facet_row, facet_col
        
        Potential Parameters for Histogram:
        x, y, pattern_shape, facet_row, facet_col, orientation
        
        Potential Parameters for Area Chart:
        x, y, line_group, facet_row, facet_col, orientation
        
        Potential Parameters for Box and Whisker Plot:
        x, y, facet_row, facet_col, orientation
        
        Potential Parameters for Heat Map:
        img, labels, facet_row, facet_col
        
        Potential Parameters for Bubble Chart:
        x, y, size, color, facet_row, facet_col

        Potential Parameters for StackedBar Chart:
        x, y, orientation="v", color="z"

        Potential Parameters for Waterfall Chart:
        x, y, orientation,text, base, measure 
        
        The must included parameters for TextBox: 
        s, v
        s is the column name and v is the output value
        """

    # Added this SAR4
    st = ""
    if df.shape[1] < 3:
        st = f"""2. Identify the user intent from user input. The intents are Comparison, Distribution, Relationship & Composition.
        3. If intent is Comparison, possible charts: Bar Chart, Line Chart
        4. If intent is Relationship, possible charts: Bubble Chart, Scatter Plot, Heat Map
        5. If intent is Distribution, possible charts: Box Chart, Pie Chart, Histogram
        6. If intent is Composition, possible charts: Pie Chart
        7. Based on above intent vs chart mapping, decide the best possible charts"""
    else:
        st = f"""2. Possible charts: GroupedBar Chart, GroupedArea Chart, StackedBar Chart
        3. Decide the best possible charts
        """

    # Updated 1st point
    prompt_template = """
        You are expert in finding chart or graph types. Given user input, number of rows in the data,number of columns in the data, list of possible chart types and list of chart parameters to consider,  
        your task is to analyze them and determine the type of chart from it.
        
        Steps to identify the correct chart types are listed below, but you should not restrict to only these rules, follow best judgement to decide correct charts:
        1. First understand the user input and sample data.Please suggest the 'TextBox' chart only if the number of rows in the data is 1 and the number of columns is also 1. Do not include any other chart names in this case. Additionally, do not suggest the 'TextBox' chart in any other scenarios
           {sql_table_properties}
        
        
        You should provide the following output in json format.
        1. The best or most suitable chart type as the output. 
        If there are more than 1 possible chart types, list the three most suitable. 
        2. For each chart, find out column names for parameters
        for example: x, y, color, orientation, facet_col, etc.
        3. Always include color parameter. Use a distinct column name which is appropriate. If no other column present then, color parameter can take same value as either parameter y or parameter x.
        4. The parameter for orientation can only take values 'v' or 'h'.
        5. For each chart, provide the confidence level, 
        a value between 0 and 1 with 1 meaning highest confidence.
        6. Sort chart in descending order of confidence level.
        7. x, y parameters must have 1 column name each from following list: {solution_table_columns}
        
        The output restriction:
        1. Omit the parameters which are "null" from the output generated
        2. Value corresponding to each parameter must come from the sample data column names
        3. Always include color parameter. Use a distinct column name which is appropriate. If no other column present then, color parameter can take same value as either parameter y or parameter x

       Provide the output in this exact 'JSON' format after excluding all the keys which have null values in it. Do not provide any textual explanation:
       
       
        {{
            "chart_1": {{
                        "Chart Name": <chart1>,
                        "Confidence Level": <confidence level>,
                        x: <column name 1 from {solution_table_columns}>,
                        y: <column name 2 from {solution_table_columns}>,
                        <param3>: <column name 3> from {solution_table_columns},
                        ...
                        }},

            "chart_2": {{
                        "Chart Name": <chart2>,
                        "Confidence Level": <confidence level>,
                        x: <column name 1 from {solution_table_columns}>,
                        y: <column name 2 from {solution_table_columns}>,
                        <param3>: <column name 3> from {solution_table_columns},
                        ...
                        }}
            ...
        }}
        

        Follow this as a step-by-step approach.

        List of all possible chart types is below: 
        {graph_list}

        Below is the list of possible parameters for each chart type:
        {graph_param_def}

        Below is the number of rows in the data:
        {number_rows}
        
        Below is the number of columns in the data:
        {number_columns}
        
        user input is below: 
        {query_prompt}
        
        sample data:
        {sql_df_head}
        
        Use only these column names: {solution_table_columns} while trying to add column names to parameters.

        """

    sql_df_head = df.head().to_string()
    dict_to_replace = {
        "graph_list": ", ".join(graph_list),
        "graph_param_def": graph_param_def,
        "query_prompt": query_prompt,
        "sql_table_properties": st,
        "solution_table_columns": solution_table_columns,
        "number_rows": str(df.shape[0]),
        "number_columns": str(len(solution_table_columns)),
        "sql_df_head": sql_df_head,
    }


    plot = send_gpt_request(client, replace_values_in_string(prompt_template, dict_to_replace)
        .replace("{", "")
        .replace("}", ""),).choices[0].message.content


    cleaned_response = plot.replace('`', '').replace('json', '')

    check_success = False
    try_no = 0
    while not check_success and try_no < 2:
        try:
            response_dict = json.loads(cleaned_response)
            check_success = True
        except json.decoder.JSONDecodeError as e:
            chart_correction_prompt = f'''Here is a JSON object that might contain some formatting errors. Can you identify and correct any mistakes to ensure that it is properly formatted? json object: {cleaned_response} Ouput: corrected json only'''
            try_no += 1
            try:
                dump = send_gpt_request(client, chart_correction_prompt).choices[0].message.content
                response_dict = json.loads(dump.replace('`', '').replace('json', ''))
                check_success = True
            except json.decoder.JSONDecodeError as e:
                pass

    try:
        response_dict = remove_null_values(response_dict)
    except:
        pass

    if len(solution_table_columns) >= 3:
        for i, k in response_dict.items():
            if "GroupedBar Chart" == k["Chart Name"]:
                k["y"] = [
                    y_col
                    for y_col in df.select_dtypes(exclude="object").columns
                    if y_col != k["x"]
                ]
                if len([k["x"]] + k["y"]) < len(solution_table_columns):
                    k["color"] = "".join(
                        [
                            clr
                            for clr in solution_table_columns
                            if clr not in [k["x"]] + k["y"]
                        ]
                    )
                else:
                    try:
                        k.pop("color")
                    except:
                        pass
            
            if "StackedBar Chart" == k["Chart Name"]:
                k["y"] = [
                    y_col
                    for y_col in df.select_dtypes(exclude="object").columns
                    if y_col != k["x"]
                ]
                if len([k["x"]] + k["y"]) < len(solution_table_columns):
                    k["color"] = "".join(
                        [
                            clr
                            for clr in solution_table_columns
                            if clr not in [k["x"]] + k["y"]
                        ]
                    )
                else:
                    try:
                        k.pop("color")
                    except:
                        pass
            if "Line Chart" == k["Chart Name"]:
                k["y"] = [
                    y_col
                    for y_col in df.select_dtypes(exclude="object").columns
                    if y_col != k["x"]
                ]
                if len([k["x"]] + k["y"]) < len(solution_table_columns):
                    k["color"] = "".join(
                        [
                            clr
                            for clr in solution_table_columns
                            if clr not in [k["x"]] + k["y"]
                        ]
                    )
                else:
                    try:
                        k.pop("color")
                    except:
                        pass
    elif len(solution_table_columns) == 2:
        for i, k in response_dict.items():
            if "Line Chart" == k["Chart Name"]:
                try:
                    k.pop("color")
                except:
                    pass

    for value in response_dict.values():
        value["color_discrete_sequence"] =[
            "rgb(179, 204, 230)",  # Lightest shade
            "rgb(143, 181, 218)",
            "rgb(107, 159, 207)",
            "rgb(71, 137, 196)",
            "rgb(53, 124, 190)",
            "rgb(46, 118, 187)",
            "rgb(39, 112, 193)"  # Darkest shade (original color)
            ]
        if value["Chart Name"] in ["Bar Chart", "Scatter Plot"]:
            value["color_continuous_scale"] = "Blues"

    return response_dict


def fixed_chart(df, plot_parameters_dup):
    print("----------PPD-------",plot_parameters_dup)
    if df.shape[0] > 1:
        non_unique_col = []
        for col in df:
            if df[col].nunique() != 1:
                non_unique_col += [col]

        df = df[non_unique_col]

    solution_table_columns = list(df.columns)
    fixed_chart = {}
    main_chart = [
        "Bar Chart",
        "Line Chart",
        "Pie Chart",
        "GroupedBar Chart",
        "Scatter Plot",
        "GroupedArea Chart",
        "StackedBar Chart",
        "Waterfall Chart"
    ]
    for i, k in plot_parameters_dup.items():
        if k["Chart Name"] in main_chart:
            chart_name = k["Chart Name"]
            k.pop("Chart Name")
            k.pop("Confidence Level")
            fixed_chart[chart_name] = k
    st = [i for i in main_chart if i not in fixed_chart]

    graph_param_def = f"""
            Potential Parameters for Bar Chart:
            x, y, color, orientation
            
            Potential Parameters for Line Chart:
            x, y, orientation, facet_row
            
            Potential Parameters for Pie Chart:
            names, values

            Potential Parameters for GroupedBar Chart:
            x, y, orientation="v", color="z"

            Potential Parameters for Scatter Plot:
            x, y, size, color="z"

            Potential Parameters for GroupedArea Chart:
            x, y, pattern_shape, orientation="v", color="z"

            Potential Parameters for StackedBar Chart:
            x, y, orientation="v", color="z"

            Potential Parameters for Waterfall Chart:
            x, y, orientation,text, base, measure 
            """

    prompt_template = """
            You are expert in finding chart parameters.Given list of chart types and list of chart parameters to consider,  
            your task is to find correct chart prameters for each chart type given in this list:{sql_table_properties}.
    
            You should provide the following output in exact given json format.
            1. Plot parameters of chart type as the output. 
            2. For each chart, find out column names for parameters
            for example: x, y, color, orientation etc.
            3. Always include color parameter. Use a distinct column name which is appropriate. If no other column present then, color parameter can take same value as either parameter y or parameter x. 
            4. The parameter for orientation can only take values 'v' or 'h'. 
            5. x, y parameters must have 1 column name each from following list: {solution_table_columns}
            
            The output restriction:
            1. Omit the parameters which have null
            2. Value corresponding to each parameter must come from the following list: {solution_table_columns}
    
            Provide the output in this exact 'JSON' format delimited by triple backticks (```). Do not provide any textual explanation:
            
            ```
            {{
                "chart_1" : {{
                            "Chart Name": <from chart type list>,
                            "x": <column name 1 from {solution_table_columns}>,
                            "y": <column name 2 from {solution_table_columns}>
                            <param3>: <column name 3> from {solution_table_columns}
                            ...
                            }},
    
                "chart_2": {{
                            "Chart Name": <from chart type list>,
                            "x": <column name 1 from {solution_table_columns}>,
                            "y": <column name 2 from {solution_table_columns}>
                            <param3>: <column name 3> from {solution_table_columns}
                            ...
                            }}
                ...
            }}
            ```
            
            Follow this as a step-by-step approach.
    
            Below is the list of possible parameters for each chart type:
            {graph_param_def}
            
            sample data:
            {sql_df_head}
            
            Use only these column names: {solution_table_columns} while trying to add column names to parameters.
    
            """

    # the sql query used to obtain sample data:
    # {sql_query}

    # load sample data from sql query
    sql_df_head = df.head().to_string()

    # prompt engineering
    # SAR4 Added sql_table_properties
    dict_to_replace = {
        "graph_param_def": graph_param_def,
        "sql_df_head": sql_df_head,
        "sql_table_properties": st,
        "solution_table_columns": solution_table_columns,
    }

    plot = send_gpt_request(client, replace_values_in_string(prompt_template, dict_to_replace)
        .replace("{", "")
        .replace("}", ""),).choices[0].message.content


    cleaned_response = plot.replace('`', '').replace('json', '')
    check_success = False
    try_no = 0
    while not check_success and try_no < 2:
        try:
            response_dict = json.loads(cleaned_response)
            check_success = True
        except json.decoder.JSONDecodeError as e:
            chart_correction_prompt = f'''Here is a JSON object that might contain some formatting errors. Can you identify and correct any mistakes to ensure that it is properly formatted? json object: {cleaned_response} Ouput: corrected json only'''
            try_no += 1
            try:
                dump = send_gpt_request(client, chart_correction_prompt).choices[0].message.content
                response_dict = json.loads(dump.replace('`', '').replace('json', ''))
                check_success = True
            except json.decoder.JSONDecodeError as e:
                pass
    try:
        response_dict = response_dict
    except:
        response_dict = {"chart_1": {"Chart Name": "Textbox"}}


    for i, k in response_dict.items():
        if k["Chart Name"] in main_chart:
            chart_name = k["Chart Name"]
            try:
                k.pop("Chart Name")
            except:
                pass
            fixed_chart[chart_name] = k

    if len(solution_table_columns) >= 3:
        for i, k in fixed_chart.items():
            if "GroupedBar Chart" == i:
                k["y"] = [
                    y_col
                    for y_col in df.select_dtypes(exclude="object").columns
                    if y_col != k["x"]
                ]
                if len([k["x"]] + k["y"]) < len(solution_table_columns):
                    k["color"] = "".join(
                        [
                            clr
                            for clr in solution_table_columns
                            if clr not in [k["x"]] + k["y"]
                        ]
                    )
                else:
                    try:
                        k.pop("color")
                    except:
                        pass

            if "StackedBar Chart" == i:
                k["y"] = [
                    y_col
                    for y_col in df.select_dtypes(exclude="object").columns
                    if y_col != k["x"]
                ]
                if len([k["x"]] + k["y"]) < len(solution_table_columns):
                    k["color"] = "".join(
                        [
                            clr
                            for clr in solution_table_columns
                            if clr not in [k["x"]] + k["y"]
                        ]
                    )
                else:
                    try:
                        k.pop("color")
                    except:
                        pass
            

            if "Line Chart" == i:
                k["y"] = [
                    y_col
                    for y_col in df.select_dtypes(exclude="object").columns
                    if y_col != k["x"]
                ]
                if len([k["x"]] + k["y"]) < len(solution_table_columns):
                    k["color"] = "".join(
                        [
                            clr
                            for clr in solution_table_columns
                            if clr not in [k["x"]] + k["y"]
                        ]
                    )
                else:
                    try:
                        k.pop("color")
                    except:
                        pass

    elif len(solution_table_columns) == 2:
        for i, k in fixed_chart.items():
            if "Line Chart" == i:
                try:
                    k.pop("color")
                except:
                    pass

    return fixed_chart


def plot_graph_using_sql_query(df: pd.DataFrame, plot_parameters: dict):
    """
    Function to fetch the dataframe using the sql query and plot different types of plots using Plotly.

    Parameters:
    - sql_query: Query using which can be used to fetch the dataframe

    - df

    - plot_parameters: Dictionary containing various parameters related to plotting,such as: x, y, title
    """
    # plot name plotly function mapping
    # Added - SAR4
    plot_functions_dict = {
        "Scatter Plot": px.scatter,  # x, y
        "Bar Chart": px.bar,  # x, y
        "GroupedBar Chart": px.bar,  # x, y
        "GroupedArea Chart": px.area,
        "Line Chart": px.line,  # x, y
        "Histogram": px.histogram,  # x
        "Pie Chart": px.pie,  # names, values
        "Area Chart": px.area,  # x, y
        "Box and Whisker Plot": px.box,  # x, y
        "Heat Map": px.imshow,
        "Bubble Chart": px.scatter,  # x, y, size,
        "TextBox": None,  # s
        "StackedBar Chart": px.bar,
        "Waterfall Chart": None
    }

    # configure parameters for plotly
    plot_type = plot_parameters["Chart Name"]

    # plot chart
    chart = None

    try:
        if plot_type == "TextBox":

            # annotated_value = f"<span style='color: #4169E1; font-size: 34px'>{plot_parameters['v']}</span><br>"
            # annotated_label = f"<span style='color: #808080; font-size: 16px'>{plot_parameters['s']}</span>"
            annotated_value = f"<span style='color: #4169E1; font-size: 34px'>{df.values[0][0]}</span><br>"
            annotated_label = (
                f"<span style='color: #808080; font-size: 16px'>{df.columns[0]}</span>"
            )
            annotated_text = annotated_value + annotated_label
            chart = px.scatter(
                pd.DataFrame(), x=[None] * 5, y=[None] * 5, template="plotly_white"
            )
            chart.add_annotation(
                x=3,
                y=4,
                text=annotated_text,
                showarrow=False,
                font={"size": 20, "color": "black"},
                align="center",
                bgcolor="white",
                # height= 300, width= 300,
                # bordercolor= 'rgba(0,0,0,0.2)',
                # borderwidth=1, borderpad= 4, opacity=1
            )

            chart.update_layout(
                xaxis={"visible": False},
                yaxis={"visible": False},
                plot_bgcolor="white",
                paper_bgcolor="white",
                font={"color": "black", "size": 12},
                margin=dict(l=20, r=20, t=20, b=20),
                # height= 300, width= 300
            )
        else:
            plot_parameters.pop("Chart Name")
            plot_parameters.pop("Confidence Level")
            # Added elif for GroupedBar Chart - SAR4
            if plot_type == "HeatMap":
                chart = plot_functions_dict[plot_type](img=df, **plot_parameters)
            elif plot_type == "GroupedBar Chart":
                plot_parameters.pop('color', None)
                chart = plot_functions_dict[plot_type](
                    data_frame=df, barmode="group", **plot_parameters
                )
              
                
            elif plot_type == "StackedBar Chart":
                if(plot_parameters['color']=="Fiscal Month"):
                    plot_parameters.pop('color', None)
                chart = plot_functions_dict[plot_type](
                    data_frame=df, barmode="stack", **plot_parameters
                )
            elif plot_type == "Pie Chart":
                chart = plot_functions_dict[plot_type](data_frame=df, **plot_parameters)    
                # title = f"{plot_parameters['names']} vs {plot_parameters['values']}"
                # chart.update_layout(title=title)
            elif plot_type == "Line Chart":
                
                df[plot_parameters['x']] = pd.to_datetime(df[plot_parameters['x']]).dt.date
                chart = plot_functions_dict[plot_type](data_frame=df, **plot_parameters)
            else:
                plot_parameters['text_auto']=True
                plot_parameters['orientation']='v'
                if(plot_parameters['color']=="Fiscal Month"):
                    plot_parameters.pop('color', None)
                print(plot_parameters)
                chart = plot_functions_dict[plot_type](data_frame=df, **plot_parameters)
            # if plot_type in ["Bar Chart", "GroupedBar Chart", "StackedBar Chart"]:
            #     rounded_values = df[plot_parameters['y']].round().astype(int)
            #     chart.update_traces(text=rounded_values, textposition='outside')
                #chart.update_traces(text=df[plot_parameters['y']], textposition='outside')

        if plot_type not in ["Pie Chart", "GroupedBar Chart"]:
            chart.update_layout(
                legend_title=None,
                coloraxis_colorbar_title_text=None,
                template="plotly_white",
                yaxis_title= plot_parameters['y'][0] if isinstance(plot_parameters['y'], list) else plot_parameters['y'] ,
            )
        # print(chart)
        return chart

    except Exception as e:
        print(e)
        data = df.head(5)
        uppercase_columns = data.columns.str.upper()
        table_trace = go.Table(
            header=dict(values=uppercase_columns),
            cells=dict(values=[data[col] for col in data.columns]),
            columnwidth=[1000] * len(uppercase_columns),
        )

        chart = go.Figure(data=table_trace)
        chart.update_layout(template="plotly_white")
        return chart


def plot_fixed_chart(solution_table, dict_, main_chart, user_selection):
    try:
        chart = main_chart


        if user_selection == "Textbox":
            return json.loads(solution_table)

        elif user_selection == "Bar Chart":
            # IF DEALS WITH 1 ROW and MULTIPLE COLS CASE
            if (solution_table.shape[0] == 1) and (solution_table.shape[1] > 1):
                dict_temp = {}
                numeric_columns = list(
                    solution_table.select_dtypes(exclude="object").columns
                )
                dict_temp["x"] = numeric_columns
                dict_temp["y"] = list(solution_table[numeric_columns].values[0])
                dict_temp["color"] = numeric_columns
                dict_temp["color_discrete_sequence"] = [
                    "rgb(179, 204, 230)",  # Lightest shade
                    "rgb(143, 181, 218)",
                    "rgb(107, 159, 207)",
                    "rgb(71, 137, 196)",
                    "rgb(53, 124, 190)",
                    "rgb(46, 118, 187)",
                    "rgb(39, 112, 193)"  # Darkest shade (original color)
]
                dict_temp["labels"] = {"y": "", "x": ""}
                # dict_temp["labels"] = {"y": "VALUE", "x": "X AXIS TITLE"}  # Capitalized labels
                try:
                    dict_temp["orientation"] = dict_["Bar Chart"]["orientation"]
                except:
                    pass
                chart = px.bar(template="plotly_white", **dict_temp)
            else:
                chart = px.bar(
                    data_frame=solution_table,
                    template="plotly_white",
                    **dict_["Bar Chart"],
                )
            y_axis_title=dict_["Bar Chart"]['y'][0] if isinstance(dict_["Bar Chart"]['y'], list) else dict_["Bar Chart"]['y']
            chart.update_layout(legend_title=None, 
                                coloraxis_colorbar_title_text=None,
                                # xaxis_title="X AXIS TITLE", 
                                # yaxis_title="VALUE"
                                yaxis_title=y_axis_title.upper()
            )
            # chart.update_layout(
            # xaxis_title_text=chart.layout.xaxis.title.text.upper(),
            # yaxis_title_text=chart.layout.yaxis.title.text.upper()
            # )

        elif user_selection == "Line Chart":
            dict_temp = {}
            dict_["labels"] = {"y": "", "x": ""}
            chart = px.line(
                data_frame=solution_table, template="plotly_white", **dict_["Line Chart"]
            )
            y_axis_title=dict_["Line Chart"]['y'][0] if isinstance(dict_["Line Chart"]['y'], list) else dict_["Line Chart"]['y']
            #chart.update_layout(legend_title=None, coloraxis_colorbar_title_text=None)
            # chart.update_layout(
            # xaxis_title_text=chart.layout.xaxis.title.text.upper(),
            # yaxis_title_text=chart.layout.yaxis.title.text.upper()
            # )
            chart.update_layout(
            legend_title=None,
            coloraxis_colorbar_title_text=None,
            xaxis_title=chart.layout.xaxis.title.text.upper() if chart.layout.xaxis.title.text else None,
            yaxis_title=y_axis_title.upper()
            )

        elif user_selection == "Pie Chart":
            if (solution_table.shape[0] == 1) and (solution_table.shape[1] > 1):
                dict_temp = {}
                numeric_columns = list(
                    solution_table.select_dtypes(exclude="object").columns
                )
                dict_temp["names"] = numeric_columns
                dict_temp["values"] = list(solution_table[numeric_columns].values[0])
                dict_temp["color"] = numeric_columns
                dict_temp["color_discrete_sequence"] = [
                    "rgb(179, 204, 230)",  # Lightest shade
                    "rgb(143, 181, 218)",
                    "rgb(107, 159, 207)",
                    "rgb(71, 137, 196)",
                    "rgb(53, 124, 190)",
                    "rgb(46, 118, 187)",
                    "rgb(39, 112, 193)"  # Darkest shade (original color)
                ]
                chart = px.pie(template="plotly_white", **dict_temp)
            else:
                chart = px.pie(
                    data_frame=solution_table,
                    template="plotly_white",
                    **dict_["Pie Chart"],
                )
            chart.update_layout(legend_title=None, coloraxis_colorbar_title_text=None)

        elif user_selection == "Scatter Plot":
            # IF DEALS WITH 1 ROW and MULTIPLE COLS CASE
            if (solution_table.shape[0] == 1) and (solution_table.shape[1] > 1):
                dict_temp = {}
                numeric_columns = list(
                    solution_table.select_dtypes(exclude="object").columns
                )
                dict_temp["x"] = numeric_columns
                dict_temp["y"] = list(solution_table[numeric_columns].values[0])
                dict_temp["color"] = numeric_columns
                dict_temp["color_discrete_sequence"] = [
                    "rgb(179, 204, 230)",  # Lightest shade
                    "rgb(143, 181, 218)",
                    "rgb(107, 159, 207)",
                    "rgb(71, 137, 196)",
                    "rgb(53, 124, 190)",
                    "rgb(46, 118, 187)",
                    "rgb(39, 112, 193)"  # Darkest shade (original color)
                ]
                dict_temp["labels"] = {"y": "", "x": ""}
                try:
                    dict_temp["orientation"] = dict_["Scatter Plot"]["orientation"]
                except:
                    pass
                chart = px.scatter(template="plotly_white", **dict_temp)
            else:
                chart = px.scatter(
                    data_frame=solution_table,
                    template="plotly_white",
                    **dict_["Scatter Plot"],
                )
            y_axis_title=dict_["Scatter Plot"]['y'][0] if isinstance(dict_["Scatter Plot"]['y'], list) else dict_["Scatter Plot"]['y']
            chart.update_layout(legend_title=None, coloraxis_colorbar_title_text=None, yaxis_title=y_axis_title.upper())
            # chart.update_layout(
            # xaxis_title_text=chart.layout.xaxis.title.text.upper(),
            # yaxis_title_text=chart.layout.yaxis.title.text.upper()
            # )

        elif user_selection == "GroupedBar Chart":
            # IF DEALS WITH 1 ROW and MULTIPLE COLS CASE
            if (solution_table.shape[0] == 1) and (solution_table.shape[1] > 1):
                dict_temp = {}
                numeric_columns = list(
                    solution_table.select_dtypes(exclude="object").columns
                )
                dict_temp["x"] = numeric_columns
                dict_temp["y"] = list(solution_table[numeric_columns].values[0])
                dict_temp["color"] = numeric_columns
                dict_temp["color_discrete_sequence"] = [
                    "rgb(179, 204, 230)",  # Lightest shade
                    "rgb(143, 181, 218)",
                    "rgb(107, 159, 207)",
                    "rgb(71, 137, 196)",
                    "rgb(53, 124, 190)",
                    "rgb(46, 118, 187)",
                    "rgb(39, 112, 193)"  # Darkest shade (original color)
                ]
                dict_temp["labels"] = {"y": "", "x": ""}
                try:
                    dict_temp["orientation"] = dict_["GroupedBar Chart"]["orientation"]
                except:
                    pass
                chart = px.bar(barmode="group", template="plotly_white", **dict_temp)
            else:
                solution_table = solution_table.loc[:, (solution_table > 0.01).any(axis=0)]
                chart = px.bar(
                    data_frame=solution_table,
                    barmode="group",
                    template="plotly_white",
                    **dict_["GroupedBar Chart"],
                    width=0.8
                )
            for i, trace in enumerate(chart.data):
                trace['offset'] = -0.2 + i * 0.1 
            y_axis_title=dict_["GroupedBar Chart"]['y'][0] if isinstance(dict_["GroupedBar Chart"]['y'], list) else dict_["GroupedBar Chart"]['y']
            chart.update_layout(legend_title=None, coloraxis_colorbar_title_text=None, yaxis_title=y_axis_title.upper(),bargap=0, bargroupgap=0 )
            # chart.update_layout(
            # xaxis_title_text=chart.layout.xaxis.title.text.upper(),
            # yaxis_title_text=chart.layout.yaxis.title.text.upper()
            # )

        elif user_selection == "GroupedArea Chart":
            chart = px.area(
                data_frame=solution_table,
                template="plotly_white",
                **dict_["GroupedArea Chart"],
            )
            y_axis_title=dict_["GroupedArea Chart"]['y'][0] if isinstance(dict_["GroupedArea Chart"]['y'], list) else dict_["GroupedArea Chart"]['y']
            chart.update_layout(legend_title=None, coloraxis_colorbar_title_text=None, yaxis_title_text=y_axis_title.upper())
            # chart.update_layout(
            # xaxis_title_text=chart.layout.xaxis.title.text.upper(),
            # yaxis_title_text=chart.layout.yaxis.title.text.upper()
            # )
        
        # elif user_selection == "Waterfall Chart":
        #     # Creating a waterfall chart using plotly.graph_objects
        #     chart = go.Figure(go.Waterfall(
        #         name = "Waterfall Chart",
        #         x = solution_table[dict_["Waterfall Chart"]["x"]],  # x-axis values
        #         y = solution_table[dict_["Waterfall Chart"]["y"]],  # y-axis values
        #         base = dict_["Waterfall Chart"].get("base", None),  # optional base for waterfall steps
        #         text = dict_["Waterfall Chart"].get("text", None),  # optional text labels for each step
        #         #measure = dict_["Waterfall Chart"].get("measure", None),  # optional measure (relative/total/absolute)
        #         # measure = dict_.get("measure", ['relative'] * (len(solution_table[dict_["Waterfall Chart"]["x"]]) - 1) + ['total'])
        #         measure = ['total'] * len(solution_table[dict_["Waterfall Chart"]["x"]]),
        #     ))
        #     chart.update_layout(template="plotly_white",
        #                         legend_title=None,
        #                         #waterfallgap=0.3,  # Gap between bars
        #                         #showlegend=True,
        #                         coloraxis_colorbar_title_text=None) 
                
        elif user_selection == "StackedBar Chart":
            print("if block executed for Stacked Bar")
            # If 1 row and multiple columns
            if (solution_table.shape[0] == 1) and (solution_table.shape[1] > 1):
                dict_temp = {}
                numeric_columns = list(
                    solution_table.select_dtypes(exclude="object").columns
                )
                dict_temp["x"] = numeric_columns
                dict_temp["y"] = list(solution_table[numeric_columns].values[0])
                dict_temp["color"] = numeric_columns
                dict_temp["barmode"] = 'stack'  # Ensure stacking
                dict_temp["color_discrete_sequence"] = [
                    "rgb(179, 204, 230)",  # Lightest shade
                    "rgb(143, 181, 218)",
                    "rgb(107, 159, 207)",
                    "rgb(71, 137, 196)",
                    "rgb(53, 124, 190)",
                    "rgb(46, 118, 187)",
                    "rgb(39, 112, 193)"  # Darkest shade (original color)
                ]
                dict_temp["labels"] = {"y": "", "x": ""}
                try:
                    dict_temp["orientation"] = dict_["StackedBar Chart"]["orientation"]
                except:
                    pass
                chart = px.bar(template="plotly_white", **dict_temp)
                print("executed first if")
            else:
                print("enterd else part")
                chart = px.bar(
                    data_frame=solution_table,
                    template="plotly_white",
                    barmode='stack',  # Ensure stacking
                    **dict_["StackedBar Chart"],
                )
                print("executed else part")
            y_axis_title=dict_["StackedBar Chart"]['y'][0] if isinstance(dict_["StackedBar Chart"]['y'], list) else dict_["StackedBar Chart"]['y']
            chart.update_layout(legend_title=None, 
                                coloraxis_colorbar_title_text=None,
                                yaxis_title=y_axis_title.upper())

        chart_type = chart['data'][0]['type']

        # Check if the type is one where you want to modify the axes
        if chart_type in ['bar', 'scatter', 'line']:  # Add other relevant types
            # Update axis titles to uppercase
            chart.update_layout(
                xaxis_title_text=chart.layout.xaxis.title.text.upper(),
                yaxis_title_text=chart.layout.yaxis.title.text.upper()
            )
        
        return chart

    except:
        data = solution_table.head(8)
        uppercase_columns = data.columns.str.upper()
        table_trace = go.Table(
            header=dict(values=uppercase_columns),
            cells=dict(values=[data[col] for col in data.columns]),
            columnwidth=[200] * len(uppercase_columns),
        )
        chart = go.Figure(data=table_trace)
        chart.update_layout(template="plotly_white")
        print(" Except block executed for",user_selection)
        return chart


diff_charts = [
    "Textbox",
    "Bar Chart",
    "Line Chart",
    "Pie Chart",
    "Scatter Plot",
    "GroupedBar Chart",
    "GroupedArea Chart",
    "StackedBar Chart",
    "Waterfall Chart",
    "Recommended",
]


def chart_output(df, user_input, chart_type="Recommended"):
    plot_parameters = plot_type_prompt_generation(user_input, df)
    print("---------------Plot_Parameters------------",plot_parameters)
    if plot_parameters["chart_1"]["Chart Name"] != "TextBox" or chart_type!="Recommended":
        # print("PLOT MAIN GRAPH - 1")
        plot_parameters_dup = copy.deepcopy(plot_parameters)
        print("---------------plot_parameters_dup------------",plot_parameters_dup)
        fixed_charts = fixed_chart(df, plot_parameters_dup)
        chart = plot_fixed_chart(
            df,
            fixed_charts,
            plot_graph_using_sql_query(df, plot_parameters["chart_1"]),
            chart_type,
        )
        print("chart data here:", chart)

    else:

        if (df.shape[0] == 1) and (df.shape[1] > 1):
            data = df.head(8)
            uppercase_columns = data.columns.str.upper()
            table_trace = go.Table(
                header=dict(values=uppercase_columns),
                cells=dict(values=[data[col] for col in data.columns]),
                columnwidth=[200] * len(uppercase_columns)
            )
            chart = go.Figure(data=table_trace)
            chart.update_layout(template="plotly_white")

        # If TEXT BOX CHART suggestion and solution table has > 1 ROW
        else:
            df.columns = df.columns.str.upper()
            chart = plot_graph_using_sql_query(df, plot_parameters["chart_1"])
    return chart
graph_list = [
    "Bar Chart",
    "Line Chart",
    "Pie Chart",
    "Scatter Plot",
    "Histogram",
    "Area Chart",
    "Box and Whisker Plot",
    "Heat Map",
    "Bubble Chart",
    "GroupedBar Chart",
    "StackedBar Chart",
]

def check_for_graph(input_text):
    lower_case_input = input_text.lower()
    for graph in graph_list:
        graph_name = graph.lower().replace(" chart", "")
        if graph_name in lower_case_input and "change" in lower_case_input:
            return graph
    return None

def chart_output_for_api(df, user_input, chart_type="Recommended"):
    isbox=False
    plot_parameters = plot_type_prompt_generation(user_input, df)
    print("---------------plot_parameters------------",plot_parameters)
    selected_chart = check_for_graph(user_input)
    print("@we are here----------------------------------------------")
    print(selected_chart)
    if selected_chart:
        print("@we are here----------------------------------------------")
        plot_parameters_dup = copy.deepcopy(plot_parameters)
        print("---------------plot_parameters_dup------------",plot_parameters_dup)
        fixed_charts = fixed_chart(df, plot_parameters_dup)
        chart = plot_fixed_chart(
            df,
            fixed_charts,
            plot_graph_using_sql_query(df, plot_parameters["chart_1"]),
            selected_chart,
        )
    elif plot_parameters["chart_1"]["Chart Name"] != "TextBox":
        chart=plot_graph_using_sql_query(df, plot_parameters["chart_1"])
        print("chart data here:", chart)
    else:
        isbox=True

        if (df.shape[0] == 1) and (df.shape[1] > 1):
            data = df.head(8)
            uppercase_columns = data.columns.str.upper()
            table_trace = go.Table(
                header=dict(values=uppercase_columns),
                cells=dict(values=[data[col] for col in data.columns]),
                columnwidth=[200] * len(uppercase_columns)
            )
            chart = go.Figure(data=table_trace)
            chart.update_layout(template="plotly_white")
        else:
            df.columns = df.columns.str.upper()
            chart = plot_graph_using_sql_query(df, plot_parameters["chart_1"])
    
    return chart, isbox

def clean_data_for_waterfall_chart(X_labels,Y_values):
    prompt_template = f"""
                        You are a expert in understanding and cleaning data to generate charts. Task is to preapre the data for a waterfall chart.
                        the list contained in the variable {X_labels} are the coloumn names in a dataframe. the corresponding values are contained in 
                        another variable {Y_values}.
                        requirement: 
                        1. First, check if the first column in {X_labels} represents an **overall total value**. Do this by comparing the first value in {Y_values} to the sum of the remaining values.
                        - If the first value is greater than or equal to the sum of the other values, it means the first column is the total, and the scenario is a **decomposition scenario**.
                        - If the first value is not larger, then you are dealing with an **incremental change scenario**.

                        2. **For decomposition scenario** follow below instruction and move to step 4:
                        - The first column is the total (positive value).
                        - The other columns represent the components that make up the total and should be treated as negative values.The corresponding value in {Y_values} should be -ve

                        3. **For incremental change scenario**:
                        - If a column increases the total, its corresponding value in {Y_values} should be positive.
                        - If a column decreases the total, its corresponding value should be negative.

                        4. Arrange the column names in the most appropriate order for the x-axis of the waterfall chart to show incremental changes.
                        5. Return result as JSON
                        6.Verify the response before returning. Only return coloumn names and corresponding values and no other text or special characters or any un-necessary strings

                        """
    response = send_gpt_request(client, prompt_template).choices[0].message.content.replace("```", "")
    response_dict=json.loads(response.replace('`', '').replace('json', ''))
    response_dict_js=response_dict.items()
    Y_values =[]
    X_labels = []

    for i,k in response_dict_js:
        print(f'{i}:{k}')
        Y_values.append(k)
        X_labels.append(i)
    return X_labels, Y_values



def create_waterfall_chart(solution_table):
    try:

        data = solution_table
        print("---------------------SOLUTION TABLE : ",solution_table)
        numeric_columns = list(data.select_dtypes(exclude="object").columns)
        non_numeric_columns = list(data.select_dtypes(include="object").columns)

        print("Length of numeric coloumns",len(numeric_columns))
        print("Length if non numeric column",len(non_numeric_columns))
        if len(numeric_columns) == 0 or len(non_numeric_columns) == 0:
            raise ValueError("Data does not contain appropriate numeric and non-numeric columns for the waterfall chart.")

        
        y_values = []
        x_labels = []
        for col in numeric_columns:
            y_values.extend(data[col].values)  # Take the first row for each numeric column
        for col in non_numeric_columns:
            x_labels.extend(data[col].values)
            # x_labels.extend([col] * len(data[col]))   # Use column names as labels
        print("Y-values",y_values)
        print("X-labels", x_labels)
        x_labels,y_values=clean_data_for_waterfall_chart(x_labels,y_values)

        print("Y-values",y_values)
        print("X-labels", x_labels)
        y_min = min(y_values) * 1.2  # Add some buffer (20%) to the min value
        y_max = sum(y_values)*2  # Add some buffer (20%) to the max value       
        measures = ['absolute'] + ['relative'] * (len(y_values) - 1)
        print(measures)
        chart = go.Figure(go.Waterfall(
                    name="Waterfall Chart",
                    x=x_labels,  # Use the column names for the x-axis
                    y=y_values,  # Use the column values for the y-axis
                    orientation="v",
                    text=[f'{val}' for val in y_values],  # Labels for the bars
                    measure=measures, 
                    connector=dict(line=dict(color="gray", width=1.5)),
                ))
        
        chart.update_layout(template="plotly_white",
                    
                    yaxis_title=numeric_columns[0],
                    xaxis_title=non_numeric_columns[0],
                    autosize=True,  # Allow the chart to automatically adjust its size
                    yaxis=dict(
                        autorange=True,  # Ensure the y-axis adjusts dynamically
                        fixedrange=False  # Disable fixed range for zoom flexibility
                    ),
                    xaxis=dict(
                        autorange=True  # Ensure the x-axis dynamically adjusts as well
                    ),
                    height=350,  # Set a fixed height
                    width=1000,  # Set a fixed width
                    margin=dict(l=40, r=40, t=40, b=40),  # Adjust margins to prevent overlap
                    waterfallgap=0.3)
        return chart
    except:
        data = solution_table.head(8)
        uppercase_columns = data.columns.str.upper()
        table_trace = go.Table(
            header=dict(values=uppercase_columns),
            cells=dict(values=[data[col] for col in data.columns]),
            columnwidth=[200] * len(uppercase_columns),
        )
        chart = go.Figure(data=table_trace)
        chart.update_layout(template="plotly_white")
        print(" Except block executed for WaterFall chart")
        return chart