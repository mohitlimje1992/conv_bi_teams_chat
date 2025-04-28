sql_examples = [
    {
        "input": "What are the total sales and profit?",
        "query": """
-- Calculate the sum of sales and profit columns from the dbo.orders_data table.
SELECT
  SUM(sales) AS [Total sales],
  SUM(profit) AS [Total profit]
FROM dbo.orders_data;
"""
    },
    {
        "input": "Show total sales for the Furniture category.",
        "query": """
-- Calculate the total sales specifically for dbo.product in the 'Furniture' category.
-- This requires joining dbo.orders_data with dbo.product on product_id.
SELECT
  SUM(o.sales) AS [Total Furniture sales]
FROM dbo.orders_data AS o
JOIN dbo.product AS p
  ON o.product_id = p.product_id
WHERE
  p.category = 'Furniture';
"""
    },
    {
        "input": "What were the total sales in California in 2014?",
        "query": """
-- Calculate the sum of sales for dbo.orders_data placed in California during 2014.
-- Assumes order_date is of DATE or DATETIME type.
SELECT
  SUM(sales) AS [Total sales CA 2014]
FROM dbo.orders_data
WHERE
  state = 'California'
  AND YEAR(order_date) = 2014;
"""
    },
    {
        "input": "Show sales broken down by region.",
        "query": """
-- Group dbo.orders_data by region and calculate the sum of sales for each.
SELECT
  region,
  SUM(sales) AS [Total sales]
FROM dbo.orders_data
GROUP BY
  region
ORDER BY
  [Total sales] DESC;
"""
    },
    {
        "input": "Give me the sales breakdown by region and Customer segment.",
        "query": """
-- Calculate the sum of sales, grouping by region and Customer segment.
SELECT
  region,
  [Customer segment],
  SUM(sales) AS [Total sales]
FROM dbo.orders_data
GROUP BY
  region,
  [Customer segment]
ORDER BY
  region,
  [Customer segment];
"""
    },
    {
        "input": "Which state had the highest profit?",
        "query": """
-- Find the state with the maximum total profit.
SELECT TOP 1
  state,
  SUM(profit) AS [Total profit]
FROM dbo.orders_data
GROUP BY
  state
ORDER BY
  [Total profit] DESC;
"""
    },
    {
        "input": "What is the total quantity sold for the 'Chairs' sub_category?",
        "query": """
-- Calculate the total quantity sold for products in the 'Chairs' sub_category.
SELECT
  SUM(o.quantity) AS [Total quantity Chairs]
FROM dbo.orders_data AS o
JOIN dbo.product AS p
  ON o.product_id = p.product_id
WHERE
  p.sub_category = 'Chairs';
"""
    },
    {
        "input": "List the top 3 product_names by total sales.",
        "query": """
-- Find the top 3 products by total sales.
SELECT TOP 3
  p.product_name,
  SUM(o.sales) AS [Total sales]
FROM dbo.orders_data AS o
JOIN dbo.product AS p
  ON o.product_id = p.product_id
GROUP BY
  p.product_name
ORDER BY
  [Total sales] DESC;
"""
    },
    {
        "input": "Show profit for 'Consumer' segment dbo.orders_data shipped via 'Second Class' mode.",
        "query": """
-- Calculate the total profit for the 'Consumer' segment shipped via 'Second Class'.
SELECT
  SUM(profit) AS [Total profit]
FROM dbo.orders_data
WHERE
  [Customer segment] = 'Consumer'
  AND ship_mode = 'Second Class';
"""
    },
    {
        "input": "What is the average discount for dbo.orders_data in the 'West' region?",
        "query": """
-- Calculate the average discount for orders in the 'West' region.
SELECT
  AVG(discount) AS [Average discount West region]
FROM dbo.orders_data
WHERE
  region = 'West';
"""
    },
    {
        "input": "Calculate the profit margin for each product category.",
        "query": """
-- Profit margin (%) = TotalProfit / TotalSales * 100 for each category.
WITH CategoryTotals AS (
  SELECT
    p.category,
    SUM(o.sales) AS TotalSales,
    SUM(o.profit) AS TotalProfit
  FROM dbo.orders_data AS o
  JOIN dbo.product AS p
    ON o.product_id = p.product_id
  GROUP BY
    p.category
)
SELECT
  category,
  TotalSales,
  TotalProfit,
  CASE
    WHEN TotalSales = 0 THEN 0
    ELSE ROUND((TotalProfit * 1.0 / TotalSales) * 100, 2)
  END AS [profit Margin (%)]
FROM CategoryTotals
ORDER BY
  [profit Margin (%)] DESC;
"""
    },
    {
        "input": "Show the year-over-year sales growth percentage for each region.",
        "query": """
-- Calculate YoY growth by region using LAG().
WITH YearlyRegionSales AS (
  SELECT
    YEAR(order_date) AS OrderYear,
    region,
    SUM(sales) AS RegionalSales
  FROM dbo.orders_data
  GROUP BY
    YEAR(order_date),
    region
),
LaggedSales AS (
  SELECT
    OrderYear,
    region,
    RegionalSales,
    LAG(RegionalSales, 1, 0) OVER (PARTITION BY region ORDER BY OrderYear) AS PreviousYearSales
  FROM YearlyRegionSales
)
SELECT
  OrderYear,
  region,
  RegionalSales,
  PreviousYearSales,
  CASE
    WHEN PreviousYearSales = 0 THEN NULL
    ELSE ROUND(((RegionalSales - PreviousYearSales) * 1.0 / PreviousYearSales) * 100, 2)
  END AS [YoY Growth (%)]
FROM LaggedSales
ORDER BY
  region,
  OrderYear;
"""
    },
    {
        "input": "Identify top 5 customers whose average order value is above the overall average.",
        "query": """
-- Find customers whose AvgOrderValue > global average, then take top 5.
WITH CustomerStats AS (
  SELECT
    customer_id,
    customer_name,
    SUM(sales) AS TotalCustomerSales,
    COUNT(DISTINCT order_id) AS NumberOfOrders
  FROM dbo.orders_data
  GROUP BY
    customer_id,
    customer_name
),
CustomerAvgOrderValue AS (
  SELECT
    customer_id,
    customer_name,
    CASE
      WHEN NumberOfOrders = 0 THEN 0
      ELSE TotalCustomerSales * 1.0 / NumberOfOrders
    END AS AvgOrderValue
  FROM CustomerStats
),
OverallAvgOrderValue AS (
  SELECT AVG(AvgOrderValue) AS GlobalAvgValue
  FROM CustomerAvgOrderValue
)
SELECT TOP 5
  caov.customer_id,
  caov.customer_name,
  ROUND(caov.AvgOrderValue, 2) AS [Customer Average Order Value]
FROM CustomerAvgOrderValue AS caov
CROSS JOIN OverallAvgOrderValue AS oaov
WHERE
  caov.AvgOrderValue > oaov.GlobalAvgValue
ORDER BY
  caov.AvgOrderValue DESC;
"""
    },
    {
        "input": "Rank dbo.product within each sub_category based on total profit.",
        "query": """
-- Use RANK() to order products by profit within each sub_category.
WITH ProductProfit AS (
  SELECT
    p.product_name,
    p.sub_category,
    SUM(o.profit) AS TotalProfit
  FROM dbo.orders_data AS o
  JOIN dbo.product AS p
    ON o.product_id = p.product_id
  GROUP BY
    p.product_name,
    p.sub_category
)
SELECT
  product_name,
  sub_category,
  TotalProfit,
  RANK() OVER (PARTITION BY sub_category ORDER BY TotalProfit DESC) AS [profit Rank within sub_category]
FROM ProductProfit
ORDER BY
  sub_category,
  [profit Rank within sub_category];
"""
    },
    {
        "input": "What percentage of total category sales does each sub_category contribute?",
        "query": """
-- Compute each sub_category's contribution to its category.
WITH SubcategorySales AS (
  SELECT
    p.category,
    p.sub_category,
    SUM(o.sales) AS SubcategoryTotalSales
  FROM dbo.orders_data AS o
  JOIN dbo.product AS p
    ON o.product_id = p.product_id
  GROUP BY
    p.category,
    p.sub_category
)
SELECT
  category,
  sub_category,
  SubcategoryTotalSales,
  SUM(SubcategoryTotalSales) OVER (PARTITION BY category) AS CategoryTotalSales,
  CASE
    WHEN SUM(SubcategoryTotalSales) OVER (PARTITION BY category) = 0 THEN 0
    ELSE ROUND((SubcategoryTotalSales * 1.0 / SUM(SubcategoryTotalSales) OVER (PARTITION BY category)) * 100, 2)
  END AS [Contribution to category sales (%)]
FROM SubcategorySales
ORDER BY
  category,
  [Contribution to category sales (%)] DESC;
"""
    },
    {
        "input": "List dbo.orders_data containing dbo.product from both 'Furniture' and 'Technology' categories.",
        "query": """
-- Find orders that include at least one Furniture and one Technology item.
SELECT
  o.order_id
FROM dbo.orders_data AS o
JOIN dbo.product AS p
  ON o.product_id = p.product_id
WHERE
  p.category IN ('Furniture', 'Technology')
GROUP BY
  o.order_id
HAVING
  COUNT(DISTINCT CASE WHEN p.category = 'Furniture' THEN p.product_id END) > 0
  AND
  COUNT(DISTINCT CASE WHEN p.category = 'Technology' THEN p.product_id END) > 0;
"""
    },
    {
        "input": "Compare the average profit margin for discounted vs non-discounted items per region.",
        "query": """
-- Compare profit margins (%) for discounted vs non-discounted by region.
SELECT
  region,
  CASE
    WHEN SUM(CASE WHEN discount = 0 THEN sales ELSE 0 END) = 0 THEN 0
    ELSE ROUND((SUM(CASE WHEN discount = 0 THEN profit ELSE 0 END) * 1.0
                / SUM(CASE WHEN discount = 0 THEN sales ELSE 0 END)) * 100, 2)
  END AS [AvgMargin_Nodiscount_Percent],
  CASE
    WHEN SUM(CASE WHEN discount > 0 THEN sales ELSE 0 END) = 0 THEN 0
    ELSE ROUND((SUM(CASE WHEN discount > 0 THEN profit ELSE 0 END) * 1.0
                / SUM(CASE WHEN discount > 0 THEN sales ELSE 0 END)) * 100, 2)
  END AS [AvgMargin_discounted_Percent]
FROM dbo.orders_data
GROUP BY
  region
ORDER BY
  region;
"""
    },
    {
        "input": "What are the top product categories these top 5 high-value customers are buying the most?",
        "query": """
-- Identify top 5 by AvgOrderValue, then sum sales by category.
WITH CustomerStats AS (
  SELECT
    customer_id,
    SUM(sales) AS TotalSales,
    COUNT(order_id) AS OrderCount
  FROM dbo.orders_data
  GROUP BY
    customer_id
),
CustomerAvg AS (
  SELECT
    customer_id,
    TotalSales * 1.0 / NULLIF(OrderCount, 0) AS AvgOrderValue
  FROM CustomerStats
),
OverallAvg AS (
  SELECT AVG(AvgOrderValue) AS GlobalAvgValue FROM CustomerAvg
),
TopCustomers AS (
  SELECT TOP 5 customer_id
  FROM CustomerAvg
  CROSS JOIN OverallAvg
  WHERE AvgOrderValue > GlobalAvgValue
  ORDER BY AvgOrderValue DESC
)
SELECT
  p.category,
  SUM(o.sales) AS TotalCategorySales
FROM dbo.orders_data AS o
JOIN dbo.product AS p
  ON o.product_id = p.product_id
WHERE
  o.customer_id IN (SELECT customer_id FROM TopCustomers)
GROUP BY
  p.category
ORDER BY
  TotalCategorySales DESC;
"""
    },
    {
        "input": "How frequently do these top 5 customers place orders compared to the average customer?",
        "query": """
-- Compare OrderCount of top 5 high-value customers to global average.
WITH CustomerStats AS (
  SELECT
    customer_id,
    COUNT(order_id) AS OrderCount,
    SUM(sales) AS TotalSales
  FROM dbo.orders_data
  GROUP BY
    customer_id
),
CustomerAvg AS (
  SELECT
    customer_id,
    TotalSales * 1.0 / NULLIF(OrderCount, 0) AS AvgOrderValue,
    OrderCount
  FROM CustomerStats
),
OverallAvg AS (
  SELECT
    AVG(AvgOrderValue) AS GlobalAvgValue,
    AVG(OrderCount * 1.0) AS GlobalAvgOrders
  FROM CustomerAvg
),
TopCustomers AS (
  SELECT TOP 5 customer_id
  FROM CustomerAvg
  WHERE AvgOrderValue > (SELECT GlobalAvgValue FROM OverallAvg)
  ORDER BY AvgOrderValue DESC
)
SELECT
  tc.customer_id,
  cs.OrderCount,
  ROUND(oa.GlobalAvgOrders, 2) AS [Average Orders per Customer]
FROM TopCustomers AS tc
JOIN CustomerStats AS cs
  ON tc.customer_id = cs.customer_id
CROSS JOIN OverallAvg AS oa
ORDER BY
  cs.OrderCount DESC;
"""
    },
    {
        "input": "What is the customer lifetime value (CLV) of these top customers?",
        "query": """
-- Sum profit for the top 5 high-value customers.
WITH CustomerStats AS (
  SELECT
    customer_id,
    SUM(sales) AS TotalSales,
    COUNT(order_id) AS OrderCount
  FROM dbo.orders_data
  GROUP BY
    customer_id
),
CustomerAvg AS (
  SELECT
    customer_id,
    TotalSales * 1.0 / NULLIF(OrderCount, 0) AS AvgOrderValue
  FROM CustomerStats
),
OverallAvg AS (
  SELECT AVG(AvgOrderValue) AS GlobalAvgValue FROM CustomerAvg
),
TopCustomers AS (
  SELECT TOP 5 customer_id
  FROM CustomerAvg
  WHERE AvgOrderValue > (SELECT GlobalAvgValue FROM OverallAvg)
  ORDER BY AvgOrderValue DESC
)
SELECT
  o.customer_id,
  SUM(o.profit) AS CustomerLifetimeValue
FROM dbo.orders_data AS o
WHERE
  o.customer_id IN (SELECT customer_id FROM TopCustomers)
GROUP BY
  o.customer_id
ORDER BY
  CustomerLifetimeValue DESC;
"""
    },
    {
        "input": "Are there any trends in customer acquisition source or region for these high-value customers?",
        "query": """
-- Analyze acquisition_source and region among top 5 high-value customers.
WITH CustomerStats AS (
  SELECT
    customer_id,
    SUM(sales) AS TotalSales,
    COUNT(order_id) AS OrderCount
  FROM dbo.orders_data
  GROUP BY
    customer_id
),
CustomerAvg AS (
  SELECT
    customer_id,
    TotalSales * 1.0 / NULLIF(OrderCount, 0) AS AvgOrderValue
  FROM CustomerStats
),
OverallAvg AS (
  SELECT AVG(AvgOrderValue) AS GlobalAvgValue FROM CustomerAvg
),
TopCustomers AS (
  SELECT TOP 5 customer_id
  FROM CustomerAvg
  WHERE AvgOrderValue > (SELECT GlobalAvgValue FROM OverallAvg)
  ORDER BY AvgOrderValue DESC
)
SELECT
  o.acquisition_source,
  o.region,
  COUNT(DISTINCT o.customer_id) AS NumTopCustomers
FROM dbo.orders_data AS o
WHERE
  o.customer_id IN (SELECT customer_id FROM TopCustomers)
GROUP BY
  o.acquisition_source,
  o.region
ORDER BY
  NumTopCustomers DESC;
"""
    },
    {
        "input": "How does the return rate or refund rate of these customers compare to others?",
        "query": """
-- Compare return rate of top 5 customers vs global return rate.
WITH CustomerStats AS (
  SELECT
    customer_id,
    SUM(sales) AS TotalSales,
    COUNT(order_id) AS OrderCount
  FROM dbo.orders_data
  GROUP BY
    customer_id
),
CustomerAvg AS (
  SELECT
    customer_id,
    TotalSales * 1.0 / NULLIF(OrderCount, 0) AS AvgOrderValue
  FROM CustomerStats
),
OverallAvg AS (
  SELECT AVG(AvgOrderValue) AS GlobalAvgValue FROM CustomerAvg
),
TopCustomers AS (
  SELECT TOP 5 customer_id
  FROM CustomerAvg
  WHERE AvgOrderValue > (SELECT GlobalAvgValue FROM OverallAvg)
  ORDER BY AvgOrderValue DESC
),
TopReturns AS (
  SELECT
    customer_id,
    COUNT(CASE WHEN is_returned = 1 THEN 1 END) * 1.0 / COUNT(order_id) AS ReturnRate
  FROM dbo.orders_data
  WHERE customer_id IN (SELECT customer_id FROM TopCustomers)
  GROUP BY customer_id
),
GlobalReturns AS (
  SELECT
    COUNT(CASE WHEN is_returned = 1 THEN 1 END) * 1.0 / COUNT(order_id) AS GlobalReturnRate
  FROM dbo.orders_data
)
SELECT
  tr.customer_id,
  ROUND(tr.ReturnRate * 100, 2) AS [Return Rate (%)],
  ROUND(gr.GlobalReturnRate * 100, 2) AS [Global Return Rate (%)]
FROM TopReturns AS tr
CROSS JOIN GlobalReturns AS gr
ORDER BY
  tr.ReturnRate DESC;
"""
    }
]