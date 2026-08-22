---
course: ptm2
lesson_id: "20"
title: "Foundations of Long  Short Portfolio Management 4"
module: long-short-portfolio
module_title: "Long/short portfolio construction"
duration: 01:14:38
duration_seconds: 4477.717
source: "20. Foundations of Long  Short Portfolio Management 4.mp4"
model: "ggml-large-v3-turbo.bin"
related_documents:
  - "Documents/Video 20/Calculating_Beta.xlsx"
---

# 20 — Foundations of Long  Short Portfolio Management 4

Okay guys, here we go. We're at video 20 now. And in this one, I'm going to explain the concept of beta. So why it's useful to us and how we can calculate it at both the equity level and the portfolio level as well. I'm going to start by explaining what beta is and why it's useful. And then I'll move on to show you the model behind beta using an Excel example.

Following that, we'll run through some ways that you can calculate beta yourselves, both as a snapshot value and in the form of a time series for individual stocks. And then at the end of the video, we're going to look at how you can use beta at the portfolio level to give you an understanding of your market exposure. And that's going to enable you to make decisions about hedging and position sizing within the portfolio.

So what is beta? Let me give you a simplified version first. Essentially, beta is a statistic that estimates the economic sensitivity of a stock or a portfolio of stocks to the market as a whole.

And by definition, the market has a beta value of 1. And basically, that acts as a reference point from which individual stocks beta is estimated around. So if an individual stock has a beta of 2, then for a given unit of return in the market, we would expect the stock to move twice as much in the same direction.

For example, if the stock market as a whole increase by 1%, then we would expect the individual stock to increase by 2% if that stock had a beta of 2%.

Conversely, if the market decreased by 1%, we would expect the stock to decrease by 2%. So the sort of increases and decreases are magnified by a factor of beta.

So if a stock has a beta value of greater than 1, what we can say about it is that it's more economically sensitive than the market as a whole.

And if it has a value of less than 1%, we would say it's less sensitive.

Now, perhaps the easiest way to start thinking about this is in terms of cyclical and defensive equities.

So by definition, cyclical equities have earnings that are economically sensitive to the business cycle, which in turn means that the price of those equities are also sensitive to the business cycle.

So think of discretionary purchases like travel, as an example.

If the economy is in a bad way, then it's much less likely that consumers will spend lots of money on vacations.

All else being equal then, we could guess that these companies have a beta value of greater than 1 because we would expect that their stock prices are more sensitive than the market as a whole to these economic fluctuations.

And conversely, we can think of defensive stocks like grocery stores at the opposite end of the scale.

People need to buy groceries irrelevant of the economic situation.

And so those companies are likely to be less sensitive to economic fluctuations than the market as a whole.

As a little detour for a moment, if you take a look at the sheet I've got open here, it contains details, including beta values, on a large list of US equities.

And included in that list are almost 5,000 companies with GICS sector and industry classifications, so that's G-I-C-S classifications, along with market cap data and beta values.

All of these values are accurate as of the 11th of September 2021.

And so most likely they aren't going to be applicable for your own work in the future, but I did want to include them just so that you had an idea of what the beta values for these companies were at the time of filming.

As well as that, perhaps more usefully, I've aggregated all of the stock data to come up with market-weighted beta values for every GICS sector, subsector, industry group and industry.

And those values are unlikely to change very much in the near future, so they will give you a good idea of what sectors and industries are sort of sensitive, more sensitive and less sensitive to the economic cycle.

Anyway, let me now dive in a little bit deeper and talk to you about where the statistic of beta that we're discussing here actually stems from.

And it comes from a couple of different financial models, namely the single index model and the capital asset pricing model, but they both use basically the same theory.

The idea of these models is to explain the returns of an asset using a single factor, so the returns of the market.

And any error or excess return in these models is identified as either sort of firm-specific risk or something called alpha, depending on the model and the context in which it's being used.

None of that stuff sort of really matters, all we're concerned with here is that we can create a simple model that estimates how much a stock moves in relation to the market based on past data.

That gives us a value called beta, and we can then use that number to accomplish various things like hedging risks or understanding portfolio exposure, position sizing and volatility estimation.

And we're going to be doing some of that stuff later in the video through some practical Excel work.

Okay, I've made a lot of references to the market so far, and you might be wondering what I actually mean by that.

Basically, when I say the market, I typically mean the whole equity market that's related to the stock that we're analysing.

So for US stocks, that would be the US equity market.

Now, it's not very easy to get returns data for the entire US stock market on aggregate.

And so what we can do is use an approximation for the market by looking at the returns for US stock indices like the S&P 500.

And as it turns out, the S&P 500 is actually a pretty good approximation for the market as a whole, because it accounts for the majority of economic output of listed companies.

So let's have a look at the spreadsheet now, and to start things off, I'm going to talk about something called a simple linear regression model, which defines an equation with which we can then retrieve beta from.

Okay, as you can see here, there's four sheets in this workbook, which, by the way, you'll be able to download yourselves in the downloads area for this video.

We're going to work from right to left here, starting with calculating beta at the individual asset level, and then moving up to the portfolio level at the end of the video.

All right, so let's look at this equity beta sheet first, and I'll explain what's going on here.

What we've got is a sheet prefilled with weekly prices and returns for the S&P 500 and two stocks, Sanderson Farms and Fluor Corporation.

Prices are in columns B to D, and returns are in columns E through G.

On the right-hand side of the sheet, there are some short company descriptions for each stock, and they describe the sort of business that they're in.

So if you take a look, Sanderson Farms is basically a poultry company, whilst Fluor Corporation is an engineering business.

Now, in the middle of the sheet, I've got a scatterplot chart showing the weekly returns data for both Sanderson Farms and the S&P 500, where Sanderson Farms returns are plotted on the y-axis, and S&P 500 returns are plotted on the x-axis.

So each dot on the chart basically represents a weekly observation for the two sets of returns.

So for example, if we look at the 25th of June observation here, we can see that Sanderson Farms returned 24.61% that week, and the S&P 500 returned 2.74%.

In the chart, that would be one of these dots that you can see around here.

And we know that because if we look across from those points to the y-axis, you can see the return value for Sanderson Farms is around 25%.

Whilst if we look down from those points to the x-axis, you can also observe that the value for S&P returns is around 2.5%.

As well as the dots representing each weekly observation in our data, I've also got a black dotted line running through all of these points, which actually represents what's called a simple linear regression line.

That line's calculated by minimizing the summed squared vertical distances between all observations and their means, which is known as the ordinary least squared method.

However, you know, you guys don't really need to know that.

You guys can just think of it basically as a line of best fit through all of this data.

Anyway, that line can be represented by an equation known as the regression equation.

And in this example, I've written that in the top right of the chart.

So the equation is y equals 0.5656x plus 0.0022.

Now, for those of you that can remember back to your high school maths, you'd know that this equation is in the form of a straight line.

When I was at school, we learned that in the form of y equals mx plus c, where every y value could be worked out as some coefficient m multiplied by the related x observation plus some constant.

So what does that actually mean?

Well, our y observations here are our Sanderson farm returns and our x observations are S&P 500 returns.

So the model equation estimates on average that the returns for Sanderson farms are equal to multiplying the S&P 500 returns over the same period by 0.5656 and adding 0.0022 or 0.22%.

Now, remember earlier when I described what beta was.

It's essentially a measure of sensitivity of a stock's returns to the market or the S&P 500 in this case.

So the value of sensitivity here can simply be measured by calculating the gradient of this line, since that represents the change in predicted Sanderson farm returns given a unit change in S&P 500 returns.

The gradient of a straight line is just the coefficient of the equation before the x observation.

So in the case of the slope or gradient here, it's 0.5656.

That means, for example, if S&P 500 returns are expected to increase by 5%, then Sanderson farms returns would be expected to increase by 5% multiplied by that 0.5656 number, which is about 2.8%.

So let's go through a quick calculation example using the equation just to reinforce that concept.

If our x value, S&P 500 returns, that is, measures 0%, then the regression model equation we have predicts that our y value, which is our Sanderson farm returns, should be equal to 0.5656 times by 0 plus 0.0022, okay?

And that is obviously just the constant at the end, which is 0.22%.

If the S&P 500 return measures 5%, then our regression equation predicts that Sanderson farms return should be 0.5656 times 5% or 0.05 plus 0.0022, which equals 0.03 roughly or 3.048%.

And you can see there that an increase in S&P 500 returns of 5% led to a predicted increase of about 2.8% in Sanderson farm returns.

Now, hopefully all of that made sense, but basically what I've done here is generate a simple linear regression line using the returns data we have for the S&P 500 and Sanderson farms.

The equation for that line represents a model that aims to predict the returns for Sanderson farms based on the returns over the same period for the S&P 500.

The gradient of the line tells us the sensitivity of Sanderson farms returns to the S&P 500, which is simply the coefficient of our X values in the equation.

So in this case, that value is 0.5656.

And that is our estimation of beta.

Since that value of beta is less than 1, it means we should expect Sanderson farms returns to be less economically sensitive than the market as a whole, as represented by the S&P 500 index.

And more specifically, it predicts, given the underlying data set that we've used, that any change in returns for Sanderson farms will be equal to around 0.5656 multiplied by the change in returns seen in the S&P 500 over the same period.

Okay, don't worry at this stage if I've lost you.

Realistically, all you need to know here is how to calculate beta for a stock, which I'm going to show you now, and also what beta represents, which we've kind of been through already.

So to that end, let me drill this home though one more time.

Beta represents the economic sensitivity of an asset.

And by definition, the market has a beta value of 1.

And so any stock that has a beta of over 1 is said to be more economically sensitive than the market.

So think cyclical sectors.

And any stock with a beta of less than 1 is said to be less economically sensitive than the market.

So think defensive sectors.

If a stock has a beta of 1, it means that a simple linear regression model predicts that for every 1% change in returns for the market, there will also be a 1% change in returns for the stock.

If a stock has a beta of 0.5, then we can estimate for every 1% change in return in the market, there is a 0.5% change in returns for the stock in the same direction.

And that's a key point here.

When beta values are positive, it means the changes will be in the same direction as the market.

In the unlikely scenario that you calculate a negative beta, then that would suggest that changes in stock returns move in the opposite direction to changes in market returns.

Okay, so you'll be pleased to know now that I'm done clarifying beta.

So let's move on to how to calculate it in Excel now.

And we can do this in a number of ways.

The first way I'm going to show you is via a scatterplot chart, as I've done here with Sanderson Farms, except this time I'm going to go through the whole process of creating the chart and the equation for Fluor Corporation.

Although this is, you know, by no means the quickest way of estimating beta, it will teach you a few more things about charting in Excel.

And I think it's always handy, really, to be able to generate scatterplot charts, given it's a great way of visualizing and understanding data and relationships between variables.

And, you know, that knowledge can be translated to other applications as well, so other data analysis applications.

So to begin with, I'm just going to select cell I-21 and then go to insert on the ribbon and choose to insert a scatterplot chart.

Once that's done, I'm going to get a blank chart area appear and I'm just going to move and resize that so that it looks roughly the same as the Sanderson Farms chart area above.

And then we're going to right-click within that chart area and go to select data to add the data series that we need.

To do that, I'm going to click the add series button on the left-hand side.

The series name is just going to be FLR versus SP500 returns.

Okay, that's just because we're plotting a scatterplot chart of our weekly observations for Fluor Corporation versus S&P 500 returns here.

Now, our X values are going to be our market returns, our S&P 500 returns, and our Y values are going to be our stock returns.

And that has to be the case whenever you're calculating beta.

Y values are always going to be stock returns.

X values are always going to be market returns.

So, our X values are going to run from cell E2 down to cell, I think, E2000 and something.

Okay, so cell E2,165.

The reason why I'm making the range down to that row is so that it matches the length of our Fluor Corporation returns.

Okay, and when you're doing analysis like this, the ranges, the arrays that you pick always have to be the same length.

Okay, so that's our X values, our market returns, so our Y values are just going to be the same sort of references, but in column G.

So, from cell G2 down to cell G2165.

Then we're going to press OK and OK again.

Scroll back to the top of the chart.

And we can see that we've got sort of a baseline chart here that looks somewhat like the scatter plot chart that we've got for Sanderson Farms above.

There's a few things we need to do to tidy this up, though.

The first of which is move our X and Y axes to the edges of the chart.

So, we want the Y axis that's in the center here over to the left and the X axis in the center here down to the bottom.

So, to do that, I'm going to double-click the Y axis first, go to labels on the right-hand side in this format axis panel and choose label position as low.

Then we're going to do exactly the same thing for our X axis, so double-click that within this format axis panel.

I'm going to, so format axis panel within the axis options tab, I should say.

I'm going to go to the labels section and choose label position as low again.

Okay, so that's looking quite a lot better.

Another thing I think that we should probably do is increase the text size of these X and Y labels.

So, I'm going to click on the Y axis again, go to home on the ribbon and just knock up the text size.

Probably to 10 points for this one and the same for our X axis as well.

Okay, next what we'll do is edit our observation points themselves.

So, at the moment they're just all kind of opaque blue circles and you can see in the chart above standards and farms, they're kind of a slightly transparent circle with a border around them.

And the reason why I quite like showing dot plots with a sort of transparent center in the markers is just so that you can kind of see when there's loads and loads of them piled on top of each other because the color becomes very opaque.

So, you can kind of see where the data is really concentrated.

So, let's do that now with this series here.

So, I'm just going to click on that series.

So, any of those data points and then in the format data series panel on the right hand side, go to fill and line.

Choose the marker options down here and this is fine actually marker options can stay as circles, but if we go to the fill section of this tab, then we're going to choose solid fill and just make the transparency instead of 0% 50% and you can see that that's changed the sort of transparency of all of those markers in that chart already.

Then I'm going to go to the border section, click solid line, press OK to making these changes as we're going and make the border just the same color basically and keep the transparency as 0.

So, that's fine.

That's basically all I wanted to do there and now the charts looking pretty good.

It's we've pretty much done everything that we need to do in terms of aesthetics.

We now need to move on to plotting the kind of regression line, the line of best fit that goes through all of this data and also the regression equation that goes with it.

So, to do that, I'm selecting this chart again and I'm going to go to chart design on the ribbon, add chart element, choose trend line and linear trend line.

So, that's going to add a blue dotted line and if I double click on that blue dotted line, we can then format that.

I'm going to format it to a solid line that is black in color instead.

So, it's a bit easier to see on the background of all those blue data points.

And then within this panel, I can choose the trend line options tab at the top right here and choose to display the equation of that line on the chart and the R squared value as well.

So, I've just ticked those two checkboxes here and you can see that the equation R squared value has appeared there.

So, I'm just going to click and drag, left click and drag that to the top right so it's in the same position as we have it for Sanderson Farms and then on the home tab of the ribbon, just increase the text size again so we can see that a bit more easily.

Okay, so that's our scatter plot chart done for Fluor Corporation and we've added a simple linear regression line with the equation defined in the top right.

Now is probably a good time to mention what the R squared number is all about as well.

Basically, that's a measure of how well the linear model explains all of the data.

So, if the value is 1, it would explain all of the data perfectly and in this way, it's pretty much the same as what we saw with values of correlation. in the previous video, the greater the dispersion around the line, the weaker the model.

I include these numbers really only as a reference, they don't necessarily affect the value that we take for beta since we know we're only estimating that based on the data that we have anyway.

However, I do think it's interesting to get a basic understanding of how well the model predicts or fits the data.

Anyway, with that scatter plot chart done, we can see the regression equation equation we have to explain Fluor Corporation's returns is 1.3999 times the market return minus 0.0012.

From that, we know that the gradient of the line and hence our beta value for Fluor Corporation is at 1.3999 or let's just call it 1.4.

Let's note down our two lifetime beta values from the stocks that we're looking at now.

And I say lifetime beta because the beta values that we've estimated here are based on all of the available data that we have for these stocks going back in history.

So in cell V10, I'm going to type lifetime beta and in the cell below that V11, I'm going to type equals 0.5656 or just 0.5656, which is the beta value we have calculated for Sanderson Farms.

And before we go any further, let's think about these two beta estimates that we've got and whether they actually add up with our expectations.

Sanderson Farms is a poultry company and that's clearly in the food processing sector.

So we'd expect there to be demand for chicken irrelevant of what's going on in the broader economic cycles of both the US and the rest of the world.

So from that perspective, I think a beta estimation of well below one makes a lot of sense.

And so I'm not too worried about a significant error in that estimation purely based on economic logic in this instance.

Equally, Fluor Corporation is an engineering business providing sort of procurement, construction and fabrication services worldwide with large segments in energy, chemicals, mining and industrials.

And given those sectors drive the demand for Fluor Corporation services, we should expect that this company is quite sensitive to the economic cycle based on the fact that demand tends to fluctuate in those areas based on willingness to invest So again, this beta estimation of about 1.4 makes sense again and it sort of shows that company profits and hence returns are cyclical and more sensitive to the market as a whole.

Now, you'll be pleased to know you don't have to go through the process of building a scatterplot chart every time you want to obtain a beta value.

There are a couple of much quicker ways that being said, I did think it'd be useful to go through that charting process as you might find some of the techniques and ideas discussed useful in other applications, as I said earlier.

So let me show you a quicker method now to calculate beta by simply using a built in Excel function called the slope function.

So let's assume we want to calculate the two year beta for Sanderson Farms.

In cell V13, I'm going to type two year beta and in the cell below V14, I'm going to type in a formula which is equals slope.

Within the slope function, you can see we have two parameters to define.

This is just like we covered previously with correlation, we need to reference two arrays, one for our y values and one for our x values.

And like I said, when it comes to beta, our y values are always the stock returns and our x values are always the market returns.

And as with our correlation calculations in the previous video, the reference arrays must be the same length and over the same period as well.

So in this instance, we want a two year beta calculation, so we need to select data from row two down to row 106 for both columns F, the Sanderson Farm returns and column E, which contain our market returns.

That means the first array reference is F2 to F106 and the second one after a comma is inserted is E2 to E106.

When we close the brackets and press enter here, we can see that the calculation returns 0.45 and that is our two year beta estimate for Sanderson Farms.

Clearly, that estimate is a little bit below our previous lifetime estimation when we use the entire dataset available.

Again, this takes me back to some of the things I said in the previous video regarding the reliability of statistical estimates.

They're by no means perfect, and they are going to vary depending on the underlying data used.

The time window that you use to estimate things like beta and correlation depends on the logic that you want to use and potentially the availability of the data in the first place.

I think whenever you're making a decision on the observational data that you're using for your analysis, always remember the goal of your analysis in the first place.

So for beta and correlation, we want to use data that we think will give us the best estimate of what those values will be in the future.

Usually, that means finding a balance between using the most recent data, which arguably better reflects the current economic environment for the firm, whilst also making sure that there's enough data points to enable statistical rigor.

When it comes to beta, industry standards vary between using sort of two to five years of data on either monthly or weekly frequencies.

But I would argue that really you should be using weekly frequencies over any time up to the sort of five year time horizon.

For the most part, lifetime values are not used since both the sort of company and economic conditions have likely changed over that kind of length of period.

So with that being said, let's calculate the three and five year beta now quickly for Sanderson Farms.

So in cell W13, I'm typing three year beta and in the cell below that I'm going to type equals slope open brackets and then I'm going to choose Sanderson Farm returns going back three years.

So from F2 to F158 followed by a comma followed by selecting our market returns over the same period.

So that's E2 to E158 and I'm just typing this in because it's a little bit easier than sort of selecting to the correct row in this case and then close brackets.

Press enter and then we'll move on to the five year beta.

So in X13, I'm going to type five year beta and in the cell below X14, I'm going to type equals slope open brackets.

This time I'm using five years of weekly returns data for each data series.

So we're going to choose from F2 to F262 for Sanderson Farm returns and in the second parameter E2 to E262 for market returns and then close brackets and press enter.

So we can see here from these calculations that the three and five year betas for Sanderson Farms are 0.49 and 0.5 respectively.

So the values over all of these timeframes, lifetime included, are actually pretty close and in line with what we would say our economic logic is for this stock.

So there's definitely no sort of red flags here.

One thing I would say, though, is that you definitely don't want to get bogged down in the kind of decimal places and sort of accuracy to multiple decimal places of beta when calculating it in various ways.

Any one of these calculations will actually be good enough to use.

So don't worry too much about that stuff.

What I do want to show you, though, and this is really for those of you that are more statistically minded and perhaps thinking of going into industry, is an additional statistic that gives us an idea of the statistical accuracy of the beta measure itself.

And I'm not going to go through this in detail because it is really beyond the scope of this course, but you guys will be able to look it up afterwards if you want to.

And like I said, it might be useful for some of you that are thinking of entering industry.

So in cell V16, I'm going to type beta space SE, which stands for beta standard standard error.

Now, standard error statistics are a little bit like standard deviations, but they can apply to error terms in statistical estimates.

So basically the value we calculate for it effectively gives us a volatility for our beta estimate.

And if we assume the error terms are normally distributed, then we can apply certain probabilities to ranges of beta.

So let's calculate the beta standard error now then in cell W16.

The formula that I'm going to use here is a long one and it's not necessary to explain.

Like I said, I just want to show you quickly how you can obtain the beta standard error without dwelling too much on it.

And you can always explore it more in your own time if you want to.

So the formula is, and bear with me here, equals index, open brackets, lin est, so l-i-n-e-s-t, open brackets again, F2 to F106.

Okay, we're looking at a two year beta here, two year beta standard error, I should say, followed by a comma.

The second parameter here is going to be E2 to E106, followed by a comma, one comma, one, close brackets, comma, two, comma, one, close brackets.

Now, you might be thinking here, what on earth is that equation?

Like I said, I don't really have time to go into the formula and how it works.

You're going to have to take my word for it that this does return the beta standard error.

You can, of course, look up this sort of formula in your own time and also more about a beta standard error if you want to, like I said before.

But anyway, you can see here that the standard error value that we obtain is roughly 0.15.

So if we assume that our errors are normally distributed, then what we can say things like there is a 68% chance that the true beta lies within one standard error of our estimation, meaning 0.45 plus or minus 0.15, which is our two year beta estimate with a range of 0.15 either side of it.

So one standard error either side of it.

Alternatively, we can also say there is a 95% chance that the true beta lies between 0.45 plus or minus 0.3, which is two times the standard error around the two year estimate.

Now, if that all sounds completely confusing to you, just forget about it now.

It's irrelevant for retail trading application.

That is just a small little segment I wanted to add for those of you that are more statistically minded or are just interested in learning more about this sort of stuff.

It's not worth me spending any more time on because explaining it just isn't worth the marginal benefit of doing so.

Really, all that matters is your estimates of beta itself and not particularly worrying about the errors in the estimates themselves too much.

Just being aware that, you know, beta estimates are subject to error.

That being said, there is one more thing I briefly want to mention about how beta estimates can be adjusted, which is something that's sometimes used in industry.

So sometimes a formula is used to smooth out estimates of beta by multiplying them by two thirds and adding one third of the market beta.

The reason behind that is that in the past, over long periods of time, companies' beta values have tended towards the market beta of one.

And not only is there some statistical evidence of this, but also some economic theory underpinning it, which is simply that as businesses grow and mature, their revenues and profits gradually diversify to the point where the company starts behaving like the average market firm.

There is also some statistical rationale behind this adjusted beta measure, which is that given the average market firm has a beta of one, our best estimate of any randomly picked firm's beta should be one as well before doing any other calculations.

So therefore the sort of weighted approach of combining our best estimate of beta, which is one with our calculated beta estimation aims to reduce error on the basis of those factors.

The split in weightings of two thirds to one third is based purely on empirical evidence of the trend of thousands of companies beta over time using past data.

Now, you know, I'm not going to prove any of that.

So again, you'll have to take my word for it, but that sort of evidence does exist.

Now, my counter argument to using adjusted beta in our circumstances anyway, is that as traders, we're never seeking to take positions for long periods of time.

So we don't need to be concerned with long drawn out changes in estimations based on kind of glacial shifts in company dynamics.

So that being said, I don't think it's going to make a huge difference whichever way you measure beta on an individual asset basis.

You can argue it in different ways.

And really what I aim to do here is give you some supplementary information to increase your knowledge.

And then the path that you choose is up to you.

You can choose to ignore the additional information on beta error and adjusted beta that I've just given or look into it further and potentially use it.

Or for you guys thinking about industry, obviously, you can take note of it and bring it up where appropriate on your career path.

For most of you, I don't think it's going to make a difference.

Again, I would say some of this stuff is relevant for you going in for those of you going into industry, but that's about it.

Okay, so I'm not going to go into the process of calculating two, three and five year betas for Fluor Corporation because it's just exactly the same methodology as we used just now.

And you guys understand how to do that by now, I'm sure.

I will make sure to include it in the download file, though.

And we are about to calculate those same values anyway in the next sheet for a slightly different purpose.

Okay, let's now take a quick look at the next sheet, which is a beta time series sheet.

In a way, there's nothing new here.

What you can see here is the S&P 500 and Fluor Corporation returns along with a rolling calculation for two and three year betas.

Now, these rolling calculations are run in exactly the same way as I ran rolling correlations in the previous video.

But that being said, because we are using a slightly different function here to do it, I am going to quickly go through the process again for a five year rolling beta instead, which we can then add to the chart and I'll comment on it.

So to calculate the rolling five year beta of Fluor Corporation, all we do is use the slope function on the returns of FLR and the S&P 500 index over five year time windows running from the most current data back as far as possible.

So in cell H1, I'm going to head the column five year rolling beta and in the cell below H2, I'm going to type equals slope open brackets E2 to E262 as the first parameter array and a comma.

And then the second parameter array will be the range D2 to D262 and close brackets that defines our Y observations as Fluor Corp returns over the last five years.

So 260 weekly rows.

And our X values are S&P 500 returns over the same timeframe.

Once that cell is inputted, we can copy down the formula to row 1905.

The reason being that row 1905 is the last row here is that the calculation, that's the last sort of row that the calculation can still make use of five years of returns data in the previous rows.

So the rows below.

So now that we have our rolling five year beta estimates, let's plot them in the chart to see how they compare with our two year and three year estimates.

To do that, I'm going to select the chart and right click in the chart and choose select data.

And then we're going to add a series.

The series name is just going to be set to whatever's in cell H1.

So it's our five year beta estimate.

And the series values are going to be from H2 to H2061.

Okay, so that's our rolling five year beta estimates from row two to row 2061.

And the reason why we're selecting an array down to that row instead of row 1905, which is actually where the data ends in that column, is that we need all of our data series that we're referencing in the chart to be the same length, which in this case is set to be equal to the longest data series that's referenced, which is our two year rolling beta series.

Okay, now that we've got our five year rolling beta estimations added to our chart, let's take a quick look at it.

Basically, what we can see and conclude here is, again, similar to the comments I gave in the previous video about rolling correlations.

Firstly, it's pretty clear that beta estimates can change and sometimes quite significantly.

So that is something that, of course, we need to be aware of whenever we're using beta estimates.

Now, I already mentioned the positives and negatives of using shorter and more recent time windows for beta calculations compared to longer windows.

So I'm not going to comment on that again.

But what I will say is that we can see from the chart here that long time windows or longer time windows clearly look less volatile than shorter time periods.

But equally, they're less responsive in times of change.

Now, each stock you look at will have a different profile in terms of rolling betas and some will be more volatile and change more than others.

And as I said before, I think whenever you're choosing the underlying data for your estimation of beta, there is no right answer.

You should just kind of strive to use a time window that makes logical sense to you, considering that you want a forward looking estimate.

So, for example, you should think through questions like, is your beta estimation based on enough data?

Is the data recent enough to reflect the current position of the firm and economic conditions?

Does the data incorporate old and stale data that perhaps isn't relevant now?

Is the period that you're grabbing data from on the whole reflective of what we think conditions will be like over the period that we're looking to trade the stock?

And I guess actually that's the big one that you need to think about.

Like I said previously, and you can use this as a guide, industry practice is to typically use two to five year beta values.

That is calculating beta from the most recent two to five year returns data.

Now, don't panic yourself too much about all of that.

You know, choosing what time period to use, because like I kind of said before, the variation in beta estimates that you get might be quite small anyway.

And, you know, the most important thing really is that you actually know how to run your own beta calculations and that you understand them so that you can then apply them.

And speaking of application, so far, all I've really told you in terms of how beta can be used is understanding whether a stock is likely to be economically sensitive or not, and perhaps whether it can be defined as a cyclical or defensive stock.

Now, it's about time we looked at some more concrete uses of beta and we're going to do that now by looking at beta at the portfolio level.

Okay, so let's go over to the portfolio beta sheet now, and this is where things become a lot more interesting.

Before I go through the sheet in more detail, as a bit of an overview, portfolio beta is basically calculated by summing the weighted beta of all its constituents.

Where the weighted beta for each position is its net weight in the portfolio multiplied by its beta.

Now, all the same rules of analyzing beta apply in the same way at the portfolio level as they did at the stock level.

And by that, I mean, it still represents the change in portfolio returns you can expect for a unit or from a unit change in the market.

So for example, a portfolio beta of one suggests the market goes up by one percent, your portfolio will also go up by one percent.

But more important than worrying about the specific percentage moves in your portfolio is being able to have a general understanding of the exposure your portfolio has to the market.

When you run a long short portfolio, you should always have an opinion on the market as a whole.

And that's what the sort of macro analysis section in this video series is all about.

And it naturally kind of dictates whether you want your portfolio to be net long, net short or market neutral.

When it comes to portfolio beta, a value of greater than zero represents a long bias, less than zero represents a short bias and zero itself is market neutral.

Now, prior to this, you might have just been thinking that your net cash exposure, that is your dollar exposure of your longs minus your shorts would represent whether your portfolio is long, short or neutral to the market.

Now, don't get me wrong, that is worth monitoring.

But the problem with that method is that it doesn't take account for the risk or portfolio or sorry, or volatility of the portfolio's constituents.

Portfolio beta is a much more accurate way to understand your exposure to the market as a whole than just your net dollar exposure.

For example, putting on $50,000 into short positions and $50,000 into long positions means you're dollar neutral.

But you might not actually have market neutral exposure once you account for the risk and volatility in your positions as measured by beta values.

Let's make things simple here in an example so I can make myself clear.

Let's say you allocated $50,000 to the long and short size of your portfolio, but your longs all have beta values of two and your shorts have beta values of 0.5.

If the market moves down 1%, then your longs are estimated to lose 2% or $1,000 and your shorts are only estimated to gain 0.5% or $250.

That's a net loss of $750 or 0.75% in the portfolio purely based on market movements, which doesn't sound very market neutral, does it?

That should provide the key motivation really for understanding your portfolio beta.

It's very important to have an idea of how your portfolio is positioned in terms of being net long, net short or market neutral so that you can make sure that it aligns with your fundamental predisposition in the sort of macro analysis that you do.

And by the way, if you have been sort of put off so far with the sort of fact that beta estimates can vary quite significantly and are prone to error, don't be for this because at the portfolio level, the error is much, much tighter.

And so portfolio beta measures tend to be more accurate than individual stock betas themselves.

And there is statistical proof of that fact, but it's not worth going into in this video.

And so again, you're just going to have to take my word for that.

Now, obviously these estimates of beta at the portfolio level still aren't perfect.

But what I'm saying here is that they are more accurate than estimates at the asset level.

Okay, so that's the goal of this sheet, calculating and understanding your portfolio beta so that you can position yourself appropriately based on your fundamental views and your conviction in those views.

As well as monitoring portfolio beta to understand your exposure to the market, this sheet will also give you more of an understanding about which of your portfolio positions carry more or less risk than others.

And monitoring these aspects should then be checked against your own fundamental views and convictions.

And then adjustments should be made accordingly if the portfolio structure isn't balanced in the way that you'd like it to be.

So let me walk you through this sheet piece by piece now.

As in the spreadsheets I've used in the previous videos, the only cells you need to edit in this sheet are the orange ones.

And they help define the positions in your portfolio and the allocation to them.

The rest of the cells are all calculation cells and so shouldn't be edited.

In terms of the layout we've got here, the top section from rows 1 to 15 represent the long side of the portfolio.

And the section below from rows 16 to 30 represent the short side of the portfolio.

Beyond that, right at the bottom, there's an aggregate section for the total portfolio.

Working from left to right now, I've split the sheet into two sections.

The blue section holds user inputs and calculation values that represent the current portfolio situation, or the one being modelled at least.

And on the right hand side, there is a green section that represents potential target scenarios such as risk parity, beta parity and equal weighting.

And I'm going to talk about those shortly.

So let me briefly run through the user inputs in this sheet.

In columns A and B, you can fill in the company name and ticker for each portfolio position that you have.

In column C, you need to enter a value of beta for each position, which can be calculated in any of the ways that we've sort of looked at in the first section of this video.

Beyond that, in columns D and E, the current price and number of shares held in each stock should be entered.

And finally, if you're looking to use any of the target scenarios in the green section, you'll need to enter your dollar target gross exposure in cell J33.

So that value should basically be the gross exposure you want for the entire portfolio, which is, you know, the sum of the gross value of all your positions added together.

That isn't the same as your margin, though, by the way, because you may well run a leverage portfolio where the overall value of positions you hold is greater than your total margin.

If you're confused about that, then hopefully it will become clear when we go through the calculation cells in the rest of the sheet.

So before I move on to looking at the calculation cells in more detail, let's consider the portfolio scenario I've set up here currently.

It should look pretty familiar to you guys because it's the same long short portfolio from the previous videos.

I've calculated beta values for each of these stocks and obtained their current prices as of the time of filming.

And so all that's left here to do is allocate some shares to each one.

Now, if you remember back to this portfolio scenario in the previous videos, we assumed an allocation of $10,000 to each position.

In reality, you can't just choose to allocate a nice round number like that to a certain stock and assume that it's going to be possible because positions need to be built up by being long or short a number of shares, each of which carry a certain price.

So only if the share price is a divisor of $10,000 would you be able to allocate $10,000 to a position nice and neatly.

However, of course, what we can do is go long or short the number of shares that gets us closest to an overall exposure of $10,000 for each position, which is what we're going to do now.

So the way we do this is just by dividing the allocation to each position by the share price and rounding it to the nearest whole number.

So, for example, for the VTRS position here, let's use a formula to calculate that in cell E3.

And that formula is just going to be equals round open brackets 10,000 divided by D3, cell D3 comma 0 close brackets.

What this formula does is use the function round to round a certain value to a desired number of decimal places.

So inside the round function, the first parameter is the number that you want to round.

So in this case, that is 10,000 because we're looking to allocate $10,000 divided by the current share price in cell D3.

And the second parameter is the number of decimal places that we want to round to.

And assuming we don't have access to fractional shares here, what we need to do is round the number of shares to the nearest whole number, which means the number of decimal places required is zero.

So hopefully that makes sense.

And you can see when we enter that formula, the number of shares required for this position is 725.

Now, instead of running that formula for all 10 positions, I've actually created an automatic target scenario in the green section, which tells you how many shares are required in each position to achieve an equal dollar weighting across all of the positions in the portfolio.

All you need to do is make sure that you have a target portfolio gross exposure set in cell J33.

So we know for this portfolio that we've got 10 positions, each with a value of $10,000 roughly.

And so we're kind of targeting a total portfolio exposure of $100,000.

And you can see here that I've already entered that value into J33.

And so if we take a look at column N now, you can see the number of shares required in every position to achieve equal dollar weightings.

From there, if we want to implement that in our portfolio model, we can just copy across those values into column E, which I'm going to do here in turn for both the long and short sides of the portfolio.

Now, when you do this, you must make sure you paste the cells as values into column E.

We don't want to copy across the formulas from column N, just the output values themselves.

So as we've done before, this is just done by right-clicking in the cells you want to copy down.

Or sorry, selecting the cells that you want to copy and pressing Ctrl C or right-clicking and clicking copy.

And then right-clicking the cell that you want to copy down from and selecting paste as values as the option from the menu, which is the clipboard option with the one, two, three on it.

When we do that, for both the long and the short positions, you can see that all of our calculation cells in columns F to I have populated.

So let's move on to what those mean now.

In column F, we've got a calculation for dollar net exposure in each position.

That is simply just the current price of each position multiplied by the number of shares multiplied by one for longs and minus one for shorts.

Column G calculates the gross exposure for each position and is almost exactly the same.

The only difference here is that it doesn't adjust for long or short positions.

So you can see here in both columns F and G that we've achieved an almost equal dollar exposure to all of our positions based on the number of shares inputted for each stock in column E.

It isn't exact, of course, because we've got rounding issues as I mentioned before, but it is close.

Now in column H, we have the net weight of each position in the total portfolio.

This is the net exposure for each position divided by the total gross exposure in the entire portfolio.

And again, this shows that we've pretty much got identical dollar percentage weightings across the board.

And finally, in column I, I've calculated what is called the net weighted beta for each position as a contribution to the total portfolio.

So these numbers are computed by taking the net weight of each position multiplied by its beta.

And when you add all of these values together, you get the overall value for portfolio beta.

And so by definition, when taken individually, they give you an idea of where risk is skewed to in the portfolio.

So, for example, since the values are a function of betas and weightings, we know that a relatively large value for net weighted beta in a certain position means that either one or both of the allocation to that position or the beta of that position is large.

And by definition, that in turn suggests that the risk carried in that position is also large.

Okay, so let's now look at the aggregated calculations for these columns.

Cells F15 and F30 show the dollar net exposure for the long and short sides of the portfolio respectively.

And when you add them together, you get the total dollar net exposure in the portfolio, which in this case is around $20,000 seen in cell F33.

That makes sense because we've got six long positions all targeting a $10,000 net exposure and four short positions each targeting a minus $10,000 net exposure.

And so when you sort of add all of that together, you get a value of $20,000 overall.

Similar calculations are run at the aggregate level for gross exposure in the adjacent cells.

And in this case, we see roughly $60,000 of exposure on the long side and almost $40,000 on the short side, which taken together equates to nearly $100,000 total gross exposure for the portfolio.

In cells H15, H30, and H33, we have aggregation cells that translate the net exposures from column F into percentage weightings by dividing them by the total gross exposure of the portfolio.

Effectively, these cells show you the percentage weighting in dollar terms assigned to the long and short sides of the portfolio.

And again, when these are summed together, you get the dollar net weight at the portfolio level, which tells you whether you're long or short biased in terms of dollar exposure and how much as a percentage of total gross exposure.

That same output can also be achieved simply by dividing the total net exposure by the total gross exposure, if that makes more sense to you.

Finally, in column I, we have aggregations of weighted beta.

Cell I33 is probably the most important cell in the sheet because it tells you the beta of your portfolio given all of the other inputs that you've defined.

And we can see this portfolio structure has a beta of 0.3, which suggests it's net long the market.

And we could estimate that if the market increased by say 10%, our portfolio would increase by around 3%.

That might sound boring to you, but running a long short portfolio usually means you're hedged against the market movements, at least partially.

And so it's very likely that you're always going to have a beta somewhere between one and minus one.

And I would expect that even more likely is that that value will be somewhere between 0.5 and minus 0.5.

As I said in previous videos, though, it doesn't necessarily mean that you should expect less return than the market for many reasons, such as, you know, the ability for this long short strategy to perform in all market conditions, as well as things like use of leverage.

And of course, your ability as a good trader to generate alpha in each sort of trade idea, meaning your ability to obtain excess returns over that which is expected for each position given its beta value and the market fluctuations.

I'll talk a little bit more about that later in the course when we get to performance metrics.

Speaking of leverage again, though, if we take this portfolio as an example, if you have put these positions on only using, say, $20,000 of margin, then you're effectively five times levered since the gross exposure of the portfolio is $100,000.

So a 3% move in your portfolio then would equate to a 15% move in your total account margin.

Now, I know that under current rules, gaining that sort of leverage, at least in the US, isn't possible unless you're kind of using options or futures.

But you get the idea of what I mean here.

The reason we build long short portfolios is to create a strategy that can succeed and build wealth in all conditions.

And it also takes advantage of things like low correlations.

And so in turn, it achieves better risk reward dynamics.

And that strategy can always then be levered up using various financial products to get closer to the kind of returns that you want to achieve.

Anyway, I don't want to dwell too much on leverage since we talk about it in other areas of the course.

Okay, so as well as beta being useful to gauge the overall market exposure your portfolio is carrying, we can also see how positions are contributing to the value of portfolio beta.

So in this scenario, on the long side, we can see that XPO is carrying over 2.5 times as much risk as TTC, since its value for net weighted beta is over 2.5 times as large.

And if we look at why that might be the case, we know that the dollar weightings in the positions of this portfolio are fairly even.

And so the additional risk with XPO must come from its value of beta.

And when we look across, we can see that that's true.

XPO's beta measures high at about 2.17, whilst TTC is quite low at 0.83.

So the profit and loss in the XPO position is likely likely to be much more volatile, purely based on market fluctuations, which is why we attribute more risk to the trade as it stands.

Now that isn't necessarily a bad thing.

It's all really down to the sort of conviction level that you have for each of your ideas.

And I'll come back to that in a little bit.

Now on the short side of things, it's looking a little bit more even.

All the net weighted betas are ranging between minus 0.155 and minus 0.121.

And so by that logic, the risk is fairly evenly distributed across those positions.

Okay, so hopefully you now understand a bit more about what net exposure is, what gross exposure is, how portfolio beta is calculated, and also how it can be analyzed both in terms of portfolio exposure and understanding the distribution of risk between positions in the portfolio.

With that in mind, let's talk through a few scenarios now, and I'll discuss how you can use some of the functionality I've built in the green section of this sheet while we're at it.

So first things first, for the current setup we have, I've already showed you how you can use column N to identify the shares required to reach equal dollar weightings in each position.

However, now we've implemented those weightings into the portfolio, we can see that risk is distributed unevenly across all of our positions based on our net weighted beta calculations.

Let's say now that for whatever reason we want to assign an even amount of risk based on values of beta to every single position in the portfolio.

So, this is a scenario calculation that I've made in columns J and K, and I've called this scenario risk parity.

And by the way, there are many professional firms that actually run this kind of sort of position sizing strategy, although, granted, this is a much more simplified version of it.

So, column J uses a fairly complex formula to calculate the gross percentage weight required in each position to achieve this.

And then column K uses whatever target gross exposure you've set in cell J33 to calculate the number of shares in each position required to achieve those weightings.

So, let's have a look at what happens when we copy those share values across into the portfolio now.

For our long positions, I'm just going to copy cells K3 to K14 and paste them as values into cell E3 by right clicking within that cell and choosing the paste as values option from the menu.

Again, I want to stress that for this procedure, you do need to copy and paste the cells as values, otherwise the spreadsheet won't work.

After doing that, I'm just going to do exactly the same for the short side of the portfolio.

Okay, let's have a look at what's happened here.

If we start in columns F2H, we can see that the dollar allocations to every position has changed and they're no longer even.

Lower beta stocks have higher exposures and vice versa in order to kind of distribute risk evenly.

By assessing the values in column I, we can see that this has been achieved quite well since every position has almost exactly the same value of weighted beta.

If we take a look at our dollar net exposure and our portfolio beta, we're still net long by both accounts.

So what have we actually done here?

Well, all this strategy does is basically define the risk for each stock based on its value of beta and then assign a percentage allocation to each position position so that the weighted risk of each position becomes the same across the whole portfolio.

If we had the same number of longs and shorts in the portfolio, this would mean we have a market neutral portfolio in beta terms, i.e. a portfolio beta of zero.

But in this case, we have more longs than shorts.

So the portfolio beta is still net long measuring 0.27.

So the next question is, is this useful to us?

And my answer to that is yes and no.

It's useful to act as a starting point for position sizing.

But logically, to keep these weightings, you would have to say that you have exactly the same level of conviction for every trade.

The reality is that that's going to be very unlikely.

You're always going to have stronger and weaker fundamental theses and these convictions will change based on price action as well.

Now, aside from ignoring conviction, another downside of this strategy is that the only way you can actually control portfolio beta and hence market exposure is by either adding or removing positions rather than adjusting weightings.

Now, we can improve on this slightly by looking at columns L and M, which model a scenario I have called beta parity.

In this model, the weightings are risk adjusted in each side of the portfolio rather than the portfolio as a whole in order to achieve beta neutrality at the portfolio level, meaning a portfolio beta of zero.

So in column L, the gross weightings are worked out in order to risk adjust all the weightings on the long side.

In this column, the weightings are worked out in two sections.

So all the long weightings add up to 100% and all the short weightings add up to 100% as well, rather than the combination of both sets of weightings summing to 100% as per, you know, we saw in the risk parity model.

Those weightings are then used to calculate the number of shares required for a portfolio with the target exposure set in cell J33.

If I copy those values into the portfolio now, you can see that market neutrality is achieved with a portfolio beta close to zero.

And as it happens, the way this calculation works also means that dollar neutrality is achieved as well.

Now, obviously, portfolio beta and the net dollar weight in the portfolio aren't zero exactly, but that's purely due to kind of rounding and the fact that we can't buy fractional shares, as I've mentioned before.

Now, I think this is a slightly better scenario model to work from as a baseline for positioning in the portfolio, since it starts with the assumption of market neutrality and risk parity within each side of the portfolio, both the long and short sides.

Now, really, these scenario models are there just as kind of head checks and guides to show you what your portfolio would look like if all you had were some position ideas, but no real conviction about the market direction or which ideas were better than others.

The reality is that you should have a fundamental view on the market, and you should have trades and ideas that you have varying levels of conviction for, because that's only natural.

So to that end, and to conclude the video, I'm not trying to persuade you by any means that you should be creating a risk or beta parity strategy in your portfolios.

Those are just interesting kind of baseline scenarios from which to work from, and I use them to help explain how this portfolio beta model works.

What you really should be using this sheet for is primarily monitoring your current portfolio and modeling any changes you're thinking of making.

And when monitoring your portfolio, you're looking for a few things.

Firstly, at the portfolio level, you want to know what your net dollar exposure is and weight is, and also your portfolio beta.

The beta value is the most important here because it's going to provide you with a more accurate idea as to whether your portfolio truly is net long, short or neutral, and by how much as well.

For most well-balanced long, short portfolios, I would expect beta to range from probably minus 0.3 to plus 0.3, but that range can widen if you're taking on a lot of leverage as I kind of discussed before.

You need to make sure that your portfolio beta is in line with your fundamental outlook on the market as a whole.

And if it isn't, then adjustments will have to be made.

And that might mean adding more weight to certain stocks or adding or subtracting entire positions as well.

Drilling down from the sort of aggregate portfolio level, you should also be monitoring the relative risk carried by each position through the net weight, that net weighted beta calculations in column I.

And remember, these values are added up to create the overall beta value for the portfolio.

And so numbers with larger magnitudes, whether positive or negative, carry more risk.

You need to make sure that you know what positions are the ones that are carrying more relative market risk and also that you're happy for that to be the case.

Again, if you aren't, then you will want to make some adjustments.

And a final point here about monitoring your portfolio in this spreadsheet is that it goes without saying that even if you keep the same positions for a long period of time, the prices of stocks and therefore weightings as well as the estimations of beta will all move around.

And so the sheet does need continuous updating.

And I would say that it's probably sensible to update the spreadsheet on either a kind of weekly basis or perhaps every other week.

And the same actually goes for the spreadsheets that we've looked at in the last few videos as well.

Now, when you're thinking of adding and subtracting positions from the portfolio, you should model how this will affect portfolio beta as a whole and use the information inside the sheet to aid decisions on weightings.

However, just like I said in the previous video, this shouldn't be your sole consideration when making structural changes to the portfolio.

All trades must first and foremost come from solid fundamental ideas with good technical timing.

And that will help create a conviction for each and every position.

And that is the kind of relative starting point really for position weightings.

After that, you should overlay how that actually fits into the portfolio using this spreadsheet and conduct a head check to see if you think the position and weighting choices that you've made are sensible.

Now, I want to make a really important point here, which I touched on earlier, but it might not have been clear enough.

Beta values represent the expected exposure of a position or portfolio to market movements.

But the returns of the position and the portfolio are driven by more than just broad market forces.

So when I say the market moves by one percent, if your portfolio beta is one, then you should expect your portfolio to move by one percent in the same direction.

That's true, but only from a market exposure point of view.

That's what would happen if your positions are kind of distinctly average.

If your ideas are high quality and generate alpha, that is excess returns above those expected by market movements, then your portfolio should perform a lot better than whatever your beta value essentially predicts.

Of course, we want to do this at an absolute minimum, but what we're really trying to target here are positions and portfolios that generate consistent absolute returns on top of alpha.

So in our portfolios, we basically want to accept some level of market risk, as we always want to have a view on the market as a whole, whether long or short.

We want to make outsized returns above market expectations predicted by beta, both on the way up and the way down.

But when we outperform on the way down, we want to try and make sure that outperformance never translates to losses.

So if the market goes down by 10% and our beta adjusted performance is say minus 5%, we are outperforming the market, but we're still losing money.

We want to target absolute performance, meaning consistent positive returns, not just outperformance.

We also typically want to use a sensible or acceptable amount of leverage to magnify portfolio volatility or exposure and hence returns when markets go up and down.

This course is built to help you get outsized absolute returns.

So don't think that your portfolio is hamstrung to perform in the way that your portfolio beta predicts because it isn't.

Beta is just there to tell you your exposure to the general direction of the market, i.e. your market risk and where risk lies in the portfolio, which aids with things like position sizing of individual trades and so on.

It's not there to predict your overall returns.

So that's the end of the video.

I hope you guys got plenty from it because once you fully get to grips with the concepts in this video and the last couple as well, you're going to have some really good knowledge and clarity about how to build high quality portfolio structures.

And it should give your stats a really good boost over time as well.

So that's it from me and I'll see you later in the video series.
