---
course: ptm2
lesson_id: "19"
title: "Foundations of Long  Short Portfolio Management 3"
module: long-short-portfolio
module_title: "Long/short portfolio construction"
duration: 01:05:06
duration_seconds: 3905.771
source: "19. Foundations of Long  Short Portfolio Management 3.mp4"
model: "ggml-large-v3-turbo.bin"
related_documents:
  - "Documents/Video 19/Portfolio_Volatility_and_Correlation.xlsm"
---

# 19 — Foundations of Long  Short Portfolio Management 3

Hi guys and welcome to video 19, Portfolio Correlation. As I said in the previous video, portfolio volatility and correlation are heavily linked and so there is going to be some overlap between what was taught in the previous video and this one, but I do think it will be useful to kind of reinforce some of the concepts to get a more in-depth understanding about correlation as a whole.

So as you can see in a break of tradition here, I'm going to start with a few PowerPoint slides in this video which will help me introduce the concept of correlation to you guys more broadly and then we're going to take that knowledge from the presentation and move over to a spreadsheet model later which is just going to kind of build on what we've covered in the previous video.

With that being said, let me formalise some of the questions I'm hoping will be answered for you in this video.

So we're going to cover what correlation is and how it's useful to traders and portfolio managers.

We're going to look at why correlation is important to consider when constructing portfolios.

How traders and portfolio managers analyse and monitor correlations within portfolios by utilising tools like Excel.

How correlation helps traders and portfolio managers make decisions to enable better performance.

And also what are some of the common pitfalls and downsides in correlation analysis.

Before we get into the weeds of correlation analysis and building on the portfolio volatility model we looked at in the last video, you need to first understand what correlation actually is.

And correlation is basically just a statistical measure that tries to quantify the extent to which two variables fluctuate together.

Or put simply, it tries to identify how the two variables are related in a linear fashion.

There are various measures of correlation, but the most common is called the Pearson coefficient of correlation.

And when I talk about correlation in this video or in the course in general, this is really the statistical measure that I'm referring to.

The Pearson coefficient of correlation is a pairwise correlation value that measures the linear relationship between two variables.

And I've got the formula up here.

And that isn't something you need to worry about remembering, but what is useful is just to have a general understanding of how that formula works.

Given that you're going to be calculating and using correlation figures in the spreadsheets that we're looking at and providing to you to help monitor and manage your own portfolios.

So one of the major misunderstandings of correlation is that people think that if the two variables that they're looking at both have positive changes in their data, it means that the relationship or correlation between them must also be positive.

And unfortunately, that's the incorrect assumption to make.

And in actual fact, what happens is that for every observation of both the X and Y variables that you're looking at, they're converted and normalized to values that represent their distances from the mean.

Not dissimilar, actually, to the methodology that we looked at in the previous video with the standard deviation calculation.

Anyway, those values are then compared to each other to compute an average relationship over the entire data set.

And that number can then be interpreted to answer whether the variables are positively or negatively related and also how strong that relationship is.

Speaking of the possible outputs of the correlation equation, another thing you ought to know is that correlation can take any value between 1 and minus 1 or 100% and minus 100%.

A value of 1 or 100% represents a perfectly positive linear relationship between two variables and a value of minus 1, which is the same as minus 100%, is a perfectly negative linear relationship.

A correlation of 0 suggests that the variables that you're looking at are perfectly uncorrelated and there is no linear relationship between them.

However, that doesn't mean that the variables are independent from each other because they could, of course, still have a relationship with each other that isn't defined in a linear fashion.

So let's have a look at some examples of what various levels of correlation look like in the form of scatterplot charts.

Now, if you don't really understand what scatterplot charts are, you don't need to worry about that too much at the moment.

You'll soon figure it out from the next slide and then you can obviously sort of rewind back to this slide if needed.

Essentially though, all I'm trying to point out here at this stage is that if there is an upward sloping relationship, so from bottom left to top right, between the two variables, then that represents a positive correlation.

And a downward sloping relationship represents a negative correlation.

The dispersion of the plots represent the strength of the relationship.

And you can see in the top row here, the more dispersed the data points are, the closer to zero the correlation value becomes.

And the gradient or the slope of the data points is actually irrelevant to the strength of relationships.

The strength of relationships is defined by the dispersion, as I said, not the gradient of the slope.

And you can see that in the bottom line of plots as well.

Okay, let's look at a real example now using real data that everyone's familiar with so that you can understand, or at least everyone sort of understands.

What we're looking at here is a scatterplot showing the relationship between major league baseball players' height and weight.

Anecdotally, of course, we would expect weight and height to have a positive relationship, which means taller people tend to be heavier and vice versa.

In this chart, height is measured in inches for each player.

And that's plotted on the x-axis, which is the horizontal axis.

And weight is measured in pounds for each player.

And that's plotted on the y-axis, which is the vertical axis.

Each dot on the chart is a data point that has a value for both height and weight.

And of course, those dots represent the major league baseball players from this sample of data.

So what can we analyze from this chart?

Well, first off, we can see the heaviest player weighs in around 290 pounds and the lightest players weigh around 150 pounds.

The tallest player measures 83 inches, whilst the shortest players are around 67 inches.

And you can see that a line of best fit has been drawn through all of these data points.

And formally, this line is calculated by minimizing the distances between all of the data points in the chart.

But you can just think of this really as the sort of average relationship between the variables height and weight.

The majority of the data points that we can see are clustered in the middle of the chart, which makes perfect sense because most people obviously have a fairly average height and weight by definition.

And if you know anything about normal distributions, then that's going to make perfect sense to you.

So anyway, when you calculate the correlation for this data, it comes out as 0.53, which is quite a strong positive linear relationship.

And you can see that reflected in the chart here.

As players height sort of deviates from the mean, so does their weight in the same direction typically.

So we have this upward sloping relationship with not too much dispersion, hence quite a strong correlation value of 0.53.

So now you have an understanding of what correlation is.

Here's a few ways that correlation analysis can be useful to traders and portfolio managers in general.

The first one is intermarket analysis.

OK, that's monitoring market and economic relationships to sort of understand the current picture and where we might be headed as well as where opportunities potentially exist.

That's a little bit like the sort of stuff that we cover in the macro sections of this video series.

It's also useful for hedging.

OK, calculating relationships between assets can be sort of helpful to reduce or hedge exposure in various ways.

So it basically allows traders to target more specific features in their returns profile.

In the next video, I'm going to talk to you about beta, which is actually sort of an extension really of correlation and a measure which is used a lot by professional traders to hedge exposure in their portfolios.

The third and final useful sort of way to use correlation is through diversification and risk in the portfolio.

And really, that's the most important use of correlation analysis.

And that's our focus as traders and portfolio managers.

And I've talked about this in the previous video and we're going to carry on with that here.

Now, you guys have seen this chart already and I talked through the principles behind it in the previous video.

It is important though, so I'm going to go through things briefly again here.

This chart really sums up why correlation between positions in your portfolio is so important to consider.

It basically shows us the benefits of diversification or really what I like to call efficient diversification.

For those of you that don't know what diversification really means, it's basically the process of pulling assets together that have diverse drivers or factors that affect their values so that the risk of the whole portfolio is reduced.

And as a reminder, in this chart, what we're looking at are various portfolios where each colored line represents a different portfolio.

And in each of these portfolios, the constituent assets are assumed to have equal capital weightings, equal volatility values and equal pairwise correlations to all of the other positions in the portfolio.

Obviously, in reality, these assumptions are far fetched, but they allow us to understand the theory of portfolio diversification much more easily.

What I'm really trying to show in this chart is that there are two core factors that affect an equally weighted portfolio's volatility, as you know.

The volatility of the assets in the portfolio and the correlations between those assets.

Now, knowing that, the next question we should have is, well, how much do each of these factors have an effect?

And the answer is that it depends on the size of the portfolio.

What we can see in this chart is that as assets are added to the portfolios, as long as the correlation of those positions is less than one, one, the risk or volatility of the portfolio falls quite significantly.

The lower the correlation, the more efficient the diversification process becomes and the faster the risk decreases.

So, for example, the blue and orange portfolios you can see both have exactly the same asset volatility assumptions.

And so, when there's only one asset in the portfolio, the volatility of the portfolio is the same, 35% on an annualized basis.

However, as assets are added to those portfolios, the volatility of the orange portfolio reduces at a much faster rate because the correlation values assumed between the constituents in that portfolio are set to 0.2 as opposed to 0.45 in the blue portfolio.

Now, let's consider that question that I mentioned previously again.

When portfolios contain just a very small number of assets, for example, one or two, then the volatilities of the individual assets are quite important to overall portfolio volatility.

However, in any reasonably sized portfolio, it's the correlation values that matter much, much more.

And we did see this in the previous video when I was looking at the variance covariance matrix and kind of running through examples there.

But you can also see it in this chart here.

So, on that point, you might be asking next whether it's a good idea to continually add positions that have relatively low correlations to the portfolio to keep reducing risk further and further.

And as I've also said previously, the simple answer to that is a resounding no.

And that is for two main reasons.

One of the primary measures of good trading is achieving what's called good risk adjusted returns, meaning your portfolio generates good returns for relatively little risk over time.

And that can be measured in a few ways.

We've already touched on the Sharpe ratio, and we're going to look at that amongst some other performance metrics as well later in the series.

If you take a look at the chart here, you'll see that there comes a point for every portfolio where adding new positions doesn't really affect the overall portfolio volatility.

The lower the correlations are of the new positions, the more risk is reduced.

But that being said, the marginal reduction in risk always diminishes with every new position.

And there comes a point usually between sort of eight to 12 positions, sometimes a bit more, where there becomes very little benefit in terms of reduced portfolio volatility.

Bearing that in mind, let's think about the return side of our risk adjusted returns metrics.

When building a portfolio, it's not unreasonable to think that the number of high quality trade ideas anyone can come up with is finite.

High quality, high conviction ideas are the positions that generate the most returns in your portfolios.

And when you add more and more positions to the portfolio, it's likely that the quality of those ideas will diminish.

So not only does adding more and more positions to the portfolio for the sake of diversification have diminishing benefits in terms of risk reduction, it also reduces your expected returns.

This process is what's known as over diversification and it can dramatically decrease your portfolio performance.

Typically, depending on the amount of capital you have to trade, you're likely going to be looking at having around eight to 12 positions on any one time in the portfolio.

As I said in the previous video, that might increase a little bit depending on the sort of total capital you have available and obviously the sort of market situation and so on.

To summarize this slide, we can see how important efficient diversification and correlation is in our portfolios.

However, we do need to be cognizant of taking things too far.

Always make sure that in your sort of prospective portfolios, positions are driven primarily by fundamental factors.

And only then should you think about correlation and portfolio construction.

And we'll talk more on that shortly.

Okay, before going on to some practical spreadsheet stuff, I want to go through a few pitfalls of correlation analysis.

And this isn't to put you off by any means, but it is there to give you a deeper understanding of how correlation works and what you might need to consider or look out for if you're using correlation values in your own analysis or portfolio.

The first one we've already covered, over diversification can lead to lower returns, both in sort of absolute and risk adjusted terms.

The second point I want to make is that correlation is not the same as causation.

What I mean by that is just because there might be a linear relationship between two variables, however strong, it doesn't mean that there is a cause and effect relationship between them.

A change in one might not cause a change in the other.

If there isn't a cause and effect relationship, then without understanding the cause factor for a correlation, then there is going to be uncertainty that the correlation will stay constant.

If we think about the previous video and our own portfolios, that obviously has implications for using assumptions of covariance or correlations in our model.

We have to appreciate that these variables are all subject to change, so that doesn't make them redundant, it just means we're trying to work with the data that we have available, but we need to be aware that that data isn't perfect.

Ideally, when it comes to building portfolios, it would be optimal to build them with positions that have very different fundamental drivers so that we can try and assure that correlations remain low going forward.

However, it's impossible to know all of the factors that affect assets, and if you thought you could get close, then they would probably change over time anyway.

A classic example of how correlations can change over time is seen in the relationship between US stocks and bonds.

This chart here shows the rolling five-year correlation between 10-year treasury prices and the S&P 500, which you can see pre-1998 was quite strongly positive, but in the next five years turned negative and has stayed that way ever since.

I'm not going to go into details as to why I think that's happened, because it's besides the point.

But what's noteworthy is that it has happened, and it's a great example of how correlations can break down or even invert.

Next one, this might sound silly to you guys, but correlation really is just a number.

It captures the linear relationship between two variables in a very specific way and based on the data in the sample that it's calculated from.

It's very easy to misinterpret, and if you really want to understand the relationship between data, then you're going to have to do more than just look at some descriptive statistics and correlations.

And Anscombe's Quartet is a classic example of this.

So Anscombe's Quartet consists of four different data sets, all with the same core descriptive characteristics.

They have the same average, variance, correlations, regression equations, and so on, which might make you think that these data sets are clearly very, very similar.

However, in this case, you'd be wrong in that assumption.

And you can see here the differences in the data sets are massive.

The point here is that correlation, like any other statistic, is just a number, and you need to understand when it's useful and when it isn't.

And often to do that, you'll have to use other investigative methods to really understand the data itself.

I mentioned that here really for two reasons.

Firstly, to warn you of the limitations of certain statistics when taken in and of themselves.

And secondly, to encourage you to go a little bit further in your own work and analysis, because that's going to give you more confidence in the outcomes that you then reach.

Another very common mistake, and one I mentioned earlier in the video, is assuming that if two data sets are trending in the same direction, then their correlation must be positive and vice versa.

If you remember back to the equation, it's calculated based on the relative difference in each observation from the mean of the data set for each variable.

But the means of each data set themselves could be very different.

So for example, if the mean return of asset X is minus 1% and the mean return of asset Y is plus 1% over all observations.

But for every sort of individual observation, when asset X returns above the mean above minus 1% and asset Y returns above its mean above 1%, then there will be a very strong positive correlation.

This concept is probably more easily illustrated through an example.

And here I've got a chart showing the price of a real estate ETF, IYR is the ticker, versus an inverse real estate ETF, REK, over the year 2020.

And as you would sort of predict, the correlation of these instruments is almost perfectly negative, it's minus 0.99.

However, if you take the trend in price of both of those funds over that year, they actually both go down.

Meaning, if you bought both at the start of the year 2020, expecting a perfect hedge, you would have actually lost money on both sides of the trade, despite a near perfect negative correlation.

The lesson here is, remember that correlation works by comparing data points to the means of the sort of X and Y variables.

So the means of the variables themselves can be very different and still yield perfect correlations.

The final pitfall that I want to talk about, which I mentioned briefly earlier as well, is common to many statistics.

And that is that the calculation itself, the correlation is dependent obviously on the data set that's used.

And can of course vary for the same two variables by looking at different samples.

So for example, using different sort of time periods or frequencies of data.

We've seen what happens to the correlation of bonds and stocks already.

But another very important situation to look at is what happens in crises when liquidity dries up in the market, for example.

In this table below, I've calculated correlations between the S&P 500 and various other assets by first filtering the days on which the VIX is at various levels to act as a proxy for liquidity levels.

And you can see that as the VIX increases, correlations across assets, particularly in equities, tends to one.

And this is actually a double whammy effect on your portfolio volatility.

Not only do individual asset volatilities increase, but also correlations magnify this effect at the portfolio level.

Okay, guys, now we've gone through some correlation theory and understand some pitfalls of correlation values themselves.

We're well prepared to plow on and look at how it can actually be useful to us.

And really, this is just going to build on the spreadsheet stuff that we looked at in the previous video.

So this spreadsheet is almost exactly the same as the one that we looked at previously with just a few extra bits added on.

The main functionality that we're going to look at is at the portfolio level in the portfolio volatility practice sheet again.

And I've made a small addition to the model here for you guys this time, which incorporates a portfolio correlation table at the bottom of the sheet.

I'm going to talk about how you can use that as sort of you're going through the process of building your own portfolios or testing different scenarios.

And we'll go back and take a look at some of the examples that we looked at in the previous video as well to get to grips with it all.

Other than that, the only major difference in this sheet is that I'm going to use this correlation function sheet to show you how to calculate correlation values yourselves for any variables that you can get data for, which may help you with your own analysis, given some of the ideas and things that we've been talking about in this video and the last one.

It's just really a sort of really useful tool to develop your understanding.

And we're going to go through a worked example with a couple of stocks.

There is one more new sheet, which you'll see here, which is the variance covariance matrix sheet.

That's just a massive covariance matrix, which I've built using all of the stocks that I've listed on the summary page.

And I just want to make a quick reference to that at some stage in the video to illustrate a point.

We'll get to that.

But first of all, I want to begin with showing you guys how to calculate correlation in Excel in this correlation function sheet.

Now, as you can see here, I've got some weekly price data for WMS.

That ticker is advanced drainage systems and OGS.

That's one gas.

This is exactly the same data that we have in the asset prices sheet for these two stocks.

And it goes back as far as mid 2015 historically.

And what we're going to do here is calculate the correlation between these two stocks using three different samples of data.

Firstly, I'm going to compute the correlation based on the entire six years of price data that we have available here.

And then I'm going to calculate both the one and two year rolling correlations and plot them in a chart so that you can see the difference.

It's all pretty simple stuff, really.

And it involves a very similar methodology.

And once we've kind of been through it, hopefully you guys will be comfortable doing this sort of correlation analysis and calculations yourselves.

So when we calculate correlations, we base it on returns rather than prices.

And so to begin with, we need to calculate all the weekly returns given our price data.

And then we can move on to the correlation function itself.

Now, as you guys know by now, calculating returns is pretty easy.

And I'm just going to do that in columns D and E quickly.

So we just take the current price divided by the previous price minus one.

That's our formula.

And then we copy down that formula for each stock in order to generate our series of returns.

As always, when we do that, we'll be left with errors at the beginning of the data series since returns on a given date require prices from the previous period.

And at the start of the series, there's no previous periods to look up prices for.

So we just delete the contents of those cells and our return series becomes one period shorter than our price series.

So with returns computed, we can now look at calculating correlation.

The function that we're going to use here to calculate correlation in Excel is just called CORAL.

So that's equals CORAL.

And if I type that in cell H1, you'll see that within the function, there are two parameters to assign.

So equals CORAL open brackets.

And we can see that there's two parameters to assign basically array one and array two.

And these are just your references to your X and Y variable data sets.

So that's just going to be the returns for WMS and OGS in this example.

It doesn't matter which data series you enter first.

But here what I'm going to do is just select all of our WMS returns data as the first parameter.

And then enter a comma to move on to array two and select all of the OGS returns data.

We're selecting all of the data available at this point because we want to calculate the historic correlation over the entire data set in this first example.

One thing to note here when using the correlation function function in Excel is that you must always use data series that are aligned and have the same number of data points.

Otherwise, it's not going to work.

So the arrays, the reference arrays for both sort of parameters, both variables need to be exactly the same length.

And if they're not the same length, it won't work.

And then obviously for your own benefit, you want to make sure that all of the prices or whatever data that you're looking at matches in each row as well for the dates that you're considering.

So with that data entered, you can see the correlation measures roughly 0.27 over the whole data set.

Let's have a look now at rolling correlations where we're going to use firstly a rolling one year window to compute correlations over using the same data series that we've just referenced previously as well.

So in column F, I'm going to head the column one year role coral.

And in cell F2, we're going to use the same correlation function equals coral.

But this time when selecting the two return series, I'm going to make sure that the arrays only account for the last year of data.

So in this example, that means putting in equals coral open brackets and we're going to select from cells D2 to D54 for the first array and cells E2 to E54 for the second array.

The reason why we're going to row 54 is because that then accounts for 52 weeks of data and that is equivalent to one year.

So over the latest year of data, you can see, and I say latest year of data because we're looking firstly in the top row at the most recent data that we have available.

So over the latest year of data, you can see the correlation has measured much less than our sort of overall correlation for the entire data set.

So the reading is 0.04 and that shows already how much correlation can change between two variables if we if we didn't already kind of anticipate that that could happen.

Let's take this a step further, though, and create a time series of one year rolling correlations.

All we need to do to do that is just copy that correlation formula down to the end of the series.

And because the cell references we used in the arrays were dynamic, so not fixed, they effectively calculate our rolling one year correlation for the entire data set.

Now, if we scroll down to the bottom of the data set, there is something that we need to address and be careful of.

Firstly, you can see that there's a few div zero errors at the end of the series.

And above these errors, there are some correlation values, but those values are only being calculated with much less data than a year's data.

So, for example, if we double click into cell F300, you'll see that it's referencing a lot of blank cells because there isn't a year of data available before the 24th of September 2015 in this data set.

So you have an option here. You can either leave values like this in and just understand that they're not using a full year of data to calculate.

Or we can just delete all the correlation cells that don't use a full one year window that we're kind of looking for.

Now, I'm going to do the latter here. And by the way, it goes without saying that you should also delete the div zero cells no matter what.

So all I'm going to do here is look at the row with the earliest returns values in, which is row 309 in this case.

And then minus 52 from that number because there's 52 weeks in a year.

That gives us row 257. And so we know that this is the last correlation calculation cell that we want in this column.

And you can double click on that cell to make sure that it's the final reference row in it is row 309.

After establishing that, all we do is select all of the calculation cells below that one and clear the content by pressing delete on the keyboard.

So we're going to do one more calculation column now where we'll compute a two year rolling correlation window rather than the one year.

And I'm going to plot these then in a line chart afterwards quickly to sort of show you the difference.

OK, so in cell G1, I'll head the column two year roll coral and in cell G2.

It's exactly the same formula as we've been using previously, except the array windows are going to be increased to incorporate two years of data, which takes us this time to row 106.

So with the formula entered, all we do is copy it down again and then delete all the correlation values in this column that don't encompass a full two years of returns data.

In this case, that means deleting the contents of all cells from cell G206 and below.

And note that when we do this, that obviously the two year correlation series that we've just created is shorter by a year than the one year rolling series that we created before.

OK, before I comment on any of these numbers, let's finish up by plotting a line chart of the two correlation series that we've just created.

You guys already know how to do this by now, so I'll just zip through this very quickly.

I'm just going to select a blank cell in the sheet somewhere, followed by navigating to insert on the ribbon and selecting a 2D line chart.

Next, I'm going to right click within the chart area, go to select data series and select the data that we want to plot.

In this chart, obviously, we're dealing with different length data sets.

So I find the easiest way to handle that is typically to reference data series and dates down to the row of the longest data series.

In this case, that's going to be the one year correlation series.

That series ends in row 257.

And so when adding each series and their respective dates, I'm just going to make sure that the reference always finishes at row 257.

So we have the data in the chart now, and I'm just going to tidy it up quickly by adding a legend and then moving the date axis to the bottom of the chart.

And first of all, to add the legend, I'm just going to select the chart and go to chart design on the ribbon, followed by add chart element, then choose legend and choose top.

So put the legend at the top of the chart.

Then to move the date labels, I'm going to double click on the date labels themselves.

And in the panel on the right hand side that appears within the axis options tab, I'm going to click on labels at the bottom and then change the label position to low.

All right.

So what can we see here?

Well, firstly, clearly correlations can change quite a bit over time.

This is an example where the correlations are particularly volatile, I think, but it does go to show that when calculating or relying on correlation values from the past, you do have to accept and understand that they're not perfect and they could easily change.

Secondly, you can see that there's quite an obvious difference in the one and two year rolling correlations.

Basically, the two year correlations are less sensitive and less volatile than the one year ones, which makes sense because more data is being used to calculate them.

In a sense, you can look at this in the same way that you might look at moving averages or anything like that.

The smaller the calculation window, the more sensitive the series and the quicker that you'll pick up any changes in the data or in the correlation in this instance.

But equally, the more unstable it is and arguably the less reliable it is in the case of correlations because it doesn't take advantage of as much data in the computation.

A similar thing can be said for taking snapshots of correlation values.

So, you know, the shorter or more and more recent window of data you use, the more timely it is and you might think that's a better indication of correlation in the future.

Or you may think using larger windows is better because there's more data involved in the calculation and quite often correlations revert to their mean.

There is no right answer here in the portfolio volatility model that I've created in this sheet.

I've used all time covariances and correlations and variances as estimates.

But you may find when you do more targeted correlation analysis using the coral function here that you prefer shorter windows.

What I would say is that I don't think it's sensible really to use anything less than a year of data.

But really the data window you use for calculating any statistics is up to you.

What I kind of wanted to point out here mostly is that you will see variation depending on the data window that you use.

And I wanted to quickly point out some of the benefits and drawbacks of using kind of longer and shorter timeframes to calculate your statistics from.

So the point of going through this little section was firstly to show you how you can quickly and easily calculate correlations yourselves in Excel for any data sets that you've been using.

Just by using the correlation function that we've looked at.

And I also wanted to build on that by showing you how to create a time series of correlation because that's going to enhance your understanding of whatever two variables it is that you're looking at in your correlation analysis.

Clearly as well this exercise also reinforced one of the pitfalls that I mentioned about correlation analysis earlier in that correlations are subject to change.

That's not exactly a pitfall.

It's just something that we have to understand and be aware of and accept because although they can change using a sample of historical data is still the only simple way to estimate what correlations might be in the future.

And it's those correlation values in the form of sort of covariances that are then fed into our portfolio volatility model in this sheet.

So with that being said, let's head back over to the portfolio volatility practice sheet now where I'm going to run through some scenarios again and this time incorporate some correlation analysis along the way.

Okay, as I said earlier, this sheet is basically the same as the one that you saw in the last video, apart from that it now also contains this correlation table, which we're going to be using in the scenarios that follow.

So to make things easy, the portfolio scenarios I'm going to go through here are exactly the same as the ones that we looked at in the previous video, except this time we're going to be looking at the correlation side of things specifically.

You'll see here, I already have our first scenario set up, which is the 10 stock portfolio that's long mega cap and large cap positions, including our FAANG stocks.

As we saw previously, the annual volatility for this portfolio is estimated at 19.23% with an average annual asset standard deviation estimation of 28.28%.

So let's now have a look at the correlations in more detail for this portfolio.

At the bottom of the sheet, I've got this correlation matrix, which as far as user input goes, works in a very similar fashion to the way the variance covariance matrix above works.

At the moment, this matrix is empty, but all we need to do to conduct our analysis is basically fill out the orange cells in columns B and AB with tickers and values that represent whether the position is a long or a short.

Because there aren't tickers entered into this correlation matrix matrix at the moment, but we do have some in the variance covariance table above, you can see that there are some warning signs in column A that basically show us a sort of caution if there is any mismatch between the tickers seen in the adjacent cells compared to the tickers seen in the representative cells in the matrix above.

So all we need to do to get started with looking at correlations in the current portfolio is enter the tickers we have in the portfolio above into column B of the correlation matrix and in the same order.

Now, you can obviously type these in manually or if you want to do things a little bit quicker, you can copy the orange cells in the portfolio table above and paste them as values as we sort of did in the previous portfolio in the previous video into the relevant cells as follows.

And you can see now that our matching signals have turned to a green tick which basically shows all of the tickers are in the right order and match those seen in the variance covariance matrix above.

Next, we need to define whether these positions are long or shorts in column AB.

In the table above, this is sort of defined implicitly really by the net allocation that we've assigned. Positive values are longs, negative values are shorts.

In this table, we're not worried about weightings, we only need to know whether each position is a long or a short.

And this is done by selecting either a 1 or a minus 1 from the dropdown menus in each cell in column AB.

Long positions should have a value of 1, short positions should have a value of minus 1.

And we're considering a long only portfolio in this scenario, so clearly all of the values here should be set to 1.

So with that done, you can now see the correlation matrix is populated with values.

Each of these values represent the pairwise correlation for the assets seen in the relevant row and column.

For example, the correlation between Apple and Microsoft is estimated at 63.95% and the correlation between Facebook and Netflix is estimated to be 40.01%.

These correlations are calculated from the full time series of returns that's been computed in the asset return sheet.

So whatever time horizon that you've got set in that sheet defines the estimates for all of our variances, covariances and correlations in this model.

The idea of this correlation matrix is that you can quickly and easily see which positions in the portfolio you expect to be more or less correlated with each other.

I've also tried to make an aggregate analysis of each position a bit easier by calculating average correlations at the end of each row in column AC.

So for example, here we can see that Microsoft has an average pairwise correlation with all the other positions in the portfolio of 53.34%.

Whilst Netflix has an average correlation value of 34.5%.

Based on these correlation values, we can see which assets have relatively high correlations and which are more effective diversifiers.

And all else being equal, you could argue that the assets with the lowest average correlations are the most important portfolio components.

Now, of course, practically speaking, there is so much more to consider, such as, you know, idea quality and its potential for returns, as well as, you know, whether these correlation values are actually reasonably estimated and indicative of future relationships between assets.

But nonetheless, it gives us a very solid insight into which assets are likely to have higher or lower correlations going forward.

As well as those average correlations for each position, I've also got a cell that calculates the average pairwise correlation across the whole portfolio, which is cell AC.74.

Currently, that's reading 42.79% for this portfolio.

This is somewhat analogous to the correlation value we saw in the diversification principles chart.

And so clearly, you know, the lower the correlation, the better in terms of risk.

Again, there are more things to consider here, such as the assumptions that all assets are equally weighted for the purposes of this correlation matrix.

And also, lower risk doesn't necessarily mean a better portfolio.

Remember, it's it's more about the risk adjusted returns of the portfolio.

So basically, this correlation matrix is useful to us because we know how important correlation is to the overall portfolio volatility.

And this matrix allows us to understand and identify where the most significant relationships between positions in our portfolio might lie.

And therefore, gives us an idea about tweaking weightings and positions to affect the overall portfolio volatility.

I'm going to stress this again, though.

Correlation analysis is important, but it shouldn't supersede fundamentals in the decision to enter trades or not.

So always remember that.

Let's look over our second scenario now, though, which is our long, large and mid cap portfolio.

I'm going to copy and paste the tickers for that portfolio from the front summary sheet here and paste them into both the variance covariance matrix and the correlation matrix inside our portfolio volatility practice sheet.

Now for this scenario, I don't need to change any orange cells in column AB since the allocations that we're assuming for the portfolio matrix are the same and the positions are all longs as well.

So the correlation matrix doesn't need updating in that column either.

So as we saw in the previous video, the portfolio volatility and average position volatility for this scenario is quite a bit higher than the last one, reading 29.36% and 44.33% respectively.

However, when we look at the correlation matrix, it's pretty clear that our average correlations are lower than the previous scenario, 38.52% versus 42.79%.

Now, these results are actually very typical of the difference between mega cap and mid cap portfolios.

Mid caps tend to have higher individual volatilities, as we know, which means they typically have greater expected returns.

But also they tend to have lower average correlations to other stocks than mega caps do, which makes them better, more efficient portfolio diversifiers as well.

And when you think about this, that makes a lot of sense because smaller companies tend to have less diversified operations.

And so their revenues, earnings and therefore stock prices are dictated by factors that are less diluted and less common to other stocks.

You can also see that the average correlation values between each position are lower.

So the maximum average correlation we see here is 45.75% assigned to ticker LEN and the minimum is 29.96% assigned to VTRS.

And by the way, these lower average correlation values in this portfolio that includes mid caps now aren't a fluke.

If you need a bit more confirmation about that, you can have a look at the variance covariance correlation matrix sheet, where I've set up a table that calculates the correlations between all of the stocks listed in this spreadsheet.

And I've aggregated them to create average correlations amongst mid caps compared to large and mega caps.

And as you'd expect, mid caps tend to have lower average correlations.

And in reality, if you were to include all US listed stocks, not just the ones I have here, the difference would be even greater.

And the results I have here, therefore, are kind of skewed in the favor of large and mega caps anyway.

I've put a couple of notes about that in the sheet here.

But basically it's because the sample size for mid caps would actually be much, much larger than how it's sort of represented here in this sheet.

So the takeaway from this scenario is again reinforcing the fact that mid caps have multiple benefits when included in our portfolios.

It's greater volatility in themselves, which gives a scope for increased expected returns, but also higher diversification benefits as well.

Now, our third and final scenario is our long short mid and large cap portfolio, where we're long six stocks, the majority being mid caps and short four stocks.

This portfolio, as I said in the previous video, is much closer to the kind of portfolio we'd expect ITPM traders to build because it utilizes long and short positions as well as mid cap stocks.

To make things easy and comparable, you'll remember we actually kept the exact exact same stocks for this portfolio as the last one.

But all we did was sort of change the allocations to include short positions.

If you remember, the top four tickers in this portfolio, which are all large cap stocks, are short positions.

And so in the volatility model, we need to change the allocations to those four positions to minus $10,000 instead of plus $10,000.

Equally for the correlation model, those four positions need to be assigned minus one values in the column AB to make them short rather than values of one.

As in the last video, when these inputs are entered, we retrieve a portfolio volatility value of 11.23% and maintain the exact same average asset volatility number of 44.33%.

That's because we're obviously using the same stocks.

We're just changing the weightings to include some shorts.

So let's have a look at the correlation matrix now for this scenario.

And it's here where we can see a massive difference in average correlations across the board.

Overall, correlations have become much, much closer to zero and some have turned negative because of the inclusion of short positions.

And that gives us an overall average portfolio correlation of minus 4.69%.

And this is the main reason why we've seen such a dramatic decrease in the portfolio volatility estimate.

Including both long and short positions has resulted in this sort of incredibly efficient diversification through these really low correlation estimates.

And all the while, we're still taking advantage of high volatility individual positions by including many mid caps.

So now we've been through those scenarios.

Let's go through a few examples using this correlation model.

So let's say that we're currently holding this portfolio, which by the way, isn't something that you should be doing when you view this course.

These trades are just examples only and they're clearly not relevant to your own kind of circumstance or probably the time that you're actually watching this series anyway.

And that goes for any kind of examples that we look out throughout look at throughout the series.

They are just examples.

You've always got to do your own work.

But anyway, for example, let's say we're holding this portfolio and we have a watch list running in the background with a bunch of great fundamentally driven ideas.

At some point, the timing of one of our ideas, let's say long temple Sealy, so TPX looks good and we're thinking about putting the position on.

Before doing so, though, we might want to see how this trade fits in our current portfolio structure.

And we can also model the effects of including it on overall portfolio volatility expectations.

And it would be nice to see how it correlates to other positions in the portfolio as well.

Assuming we have capital to spare, let's model what would happen if we include this position in the portfolio with an allocation of $10,000.

To do that, we would just enter the ticker TPX into both the volatility and correlation models and assign a capital allocation of $10,000 to the volatility matrix and a one value to the correlation matrix in column AB.

If we then take a look at the results, we can see that the overall portfolio volatility estimate has increased by about 1.5%.

And as far as correlation values go, nothing really sticks out.

TPX pairwise correlations are okay across the board.

Nothing's particularly high, not enough to cause a red flag anyway.

And the average correlation for that position to the other positions is also okay.

It's not the highest, it's not the lowest and overall it has increased the average correlation to minus 2.66%.

All pretty insignificant and that's a good sign really.

When doing this, we just want to understand how it sits, how the new position that we're looking at, sits in the portfolio and make sure that there's no obviously high correlations or increases in portfolio volatility that then might cause red flags and warrant further investigation.

The majority of the time in your own portfolios, this is going to be the case.

If both the fundamentals and technicals for a prospective position look good, it's generally going to be okay to put on, but it is still worth modeling and checking what's happening at the portfolio level to make sure that you're happy and there's no sort of red flags being raised.

Now, if you guys are really doing your work properly, you might be in a situation where you actually have a high number of quality ideas ready to go at the same time whilst also maintaining a reasonably full portfolio.

Now, if that's the case, you've got some decisions to make.

Do you want to swap any positions out?

If not, do you have any capital spare to add new ones?

If you can only add one out of, say, two or three trades, how are you going to choose?

Again, I'm always going to say that these decisions should be driven primarily by the fundamental strength of the idea and your own conviction.

However, in the scenario where you might be choosing between a couple of ideas and everything about them seems equal in terms of quality and timing, then you could use portfolio volatility and correlation modeling to sort of make what is likely the best decision at the portfolio level.

So, for example, let's say as well as TPX, we're also considering universal display core.

So OLED.

And ultimately, you think that there's nothing between these two ideas in terms of quality or conviction.

One approach to consider is modeling how the portfolio structure is affected with including each one and then making a decision based on that.

So let's remove TPX now and include OLED instead to see how things change.

So you can see here that the estimated portfolio volatility has decreased as has the average correlation inside the portfolio and OLED itself looks to be less correlated in each pairwise relationship.

Now, I wouldn't say there's a massive amount in it, but it is something.

OLED looks slightly more attractive at the portfolio level in this case.

However, that is only the risk side of things.

Perhaps we should also be expecting lower returns from OLED.

Well, if what I said before is true and everything about this trade really is on equal terms, then that should have already been considered before we even got to this point.

But if we wanted to go back and check the historical and implied volatility of the stock at this point and think about whether that changes our expectations, we could do that as well.

So those are the sorts of things that you should be thinking about in terms of modeling portfolio volatility and correlations, thinking about what your portfolio structure looks like when you add positions or change positions.

And as I've been saying throughout this video and the last video, not every bit of analysis that we're looking at here is actionable in and of itself.

It should be noted and considered in the broad context of everything else.

And once you've completed the whole course and started down the road of practical implementation yourself, you'll be in a far more informed and confident mind frame in making some of these decisions.

So that's it. There's nothing else to look at in this video.

The rest of the spreadsheet is all the same.

Please remember all of the practical implementation steps from the last video, though, because they do apply again here.

And what I mean by that is how you update and prepare all of your prices and returns data so that it feeds through correctly to the portfolio volatility and correlation models.

OK, so what are the important points to take away from this video and the last one in terms of correlation and portfolio structuring?

In the last video, we learned that a portfolio's variance is a function of both the variances and covariances of individual assets within the portfolio.

However, we found that as more assets are added to the portfolio, it's the covariance terms that become the dominant contributors to the eventual output of portfolio volatility.

We learned that the relationship between assets then, whether measured in terms of covariance or correlation, is the most important factor in portfolio diversification.

With that in mind then, it set us up with the key concept running throughout this video, which has been that correlation assessment is a hugely important factor to consider in the context of portfolio construction.

And I've talked through and demonstrated that in a number of ways.

We've discussed how efficient diversification leads to higher risk adjusted returns.

What I mean by efficient diversification is incorporating positions in the portfolio with low correlations to reduce portfolio risk at a faster rate and a higher magnitude than if we included medium or high correlation positions.

That allows us to sufficiently diversify without including so many positions that we then sacrifice the quality and conviction of our ideas, which is obviously detrimental to our expected returns.

Remember also that the more positions you add, the lower the marginal benefit of risk reduction becomes anyway.

So building a long short portfolio that predominantly incorporates mid cap stocks is a great vehicle to actually achieve this.

A mix of long and short trades is a massive aid to lower correlation positions and hence reduce risk.

And mid caps not only offer up the opportunity for higher profits than larger cap stocks, but also give us a wider range of correlations to work with.

And often they'll represent a more efficient diversifier than their larger cap counterparts as well.

So with that being said, there's a few things to consider at this point from a practical perspective.

There are many considerations in using correlation values as I covered throughout the first section of this video.

And it would be naive to assume that historical correlation always implies future correlation, since there may be events in the future that cause correlations to change, even if only temporarily.

So we've seen that in a number of examples throughout the video.

One of the most important ones being when we looked at what happens when liquidity crises occur and correlations tend to one.

There's a sort of dash for cash and all assets tend to move in the same direction.

So correlations tend to one.

I've already touched on the idea of over diversification as well, but that is another important practical consideration.

Because even in the unrealistic scenario where we assume we can find an endless number of low correlation ideas to add to the portfolio, we still need to be cognizant of the opportunity or profit side of the equation.

And what I mean by that is that over diversification tends to lead to executing lower quality and lower conviction ideas, and that can seriously damage future returns.

So there still needs to be a certain amount of concentration of positions to maximize returns whilst taking advantage of low correlations where possible.

And for the umpteenth time, correlation considerations always come after solid fundamental analysis.

Another thing I want to reiterate from the previous video is that by constructing a long short portfolio, we've seen that estimated portfolio volatility decreases significantly.

Despite the reduction in volatility, it's important to remember that that doesn't necessarily mean less opportunity for profit.

Long short portfolio strategies can work in all markets, which actually is much better for wealth creation over time.

And we talked about that in the previous video.

But not only that, as I've said before, the diversification benefits are much more efficient due to the low or negatively correlated positions, which means our risk adjusted returns can be much greater.

We can also increase upside in our returns or the opportunity side of the equation by structuring our trades with leveraged products such as options, which is something we talk about in the Professional Options Trading Masterclass video series.

Not only does that allow for magnified returns, but if it's used correctly, it can also be a really great way of managing risk as well due to their asymmetric risk profiles.

All of those concepts and the theory that we've talked about hopefully came together when we went through some examples and scenarios where I practically demonstrated how you could use the portfolio volatility and correlation spreadsheet models that I've built for you for your own purposes.

Using that spreadsheet is something that you should be doing on a pretty regular basis to help yourselves understand your own portfolios, where the risks lie and also make decisions based on your current and prospective portfolio structures.

Always remember though, with all of that in context, to successfully implement correlation analysis, you need to understand how correlation works and its pitfalls so that you don't rely too much on a single statistical number and become sort of complacent about correlation analysis.

Because, you know, correlation analysis, like everything else, is just a tool to improve the probability of success.

And it's by no means the holy grail.

Anyway, good work guys.

This volatility and correlation stuff isn't that easy to get your head around, but I'm sure you'll all get the hang of it as you watch and re-watch these videos and also play around with all the spreadsheets and practically implement what you've learned as well.

That's it for this video though.

And I'll see you in the next one where we're going to talk about portfolio beta, how you can measure it and why it's useful.
