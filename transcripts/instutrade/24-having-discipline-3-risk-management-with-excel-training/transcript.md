---
course: instutrade
lesson_id: "24"
title: "Having Discipline 3, Risk Management with Excel Training"
module: discipline-and-risk
module_title: "Discipline and risk management"
duration: 00:26:46
duration_seconds: 1605.728
source: "Anton Kreil - Professional Trading Masterclass Instutrade/24. Having Discipline 3, Risk Management with Excel Training.mp4"
model: "ggml-large-v3-turbo.bin"
related_documents:
  []
---

# 24 — Having Discipline 3, Risk Management with Excel Training

Okay, welcome back. Welcome to video number 24, where Chris is going to show you on the computer how you can actually calculate your own beta as long as you can get the data. Now, there's a couple of things here. The only reason why you would actually go and calculate your own beta is really because you can't get the beta, number anywhere else. There's a lot of online resources where you can actually get beta. So go onto all of the typical financial websites and you'll see that you'll get beta values for most stocks on most websites. What you'll typically see is the three year beta. The problem with going on these websites sometimes is that you don't actually know the length of time that you're looking at in terms of beta.

The download section, the one that you're looking at in all of the spreadsheets, the beta that you're looking at there is the five year rolling beta, which is from a company in the United States called Value Line. Now, if you have a beta of that length of time, five years, it's very, very unlikely that over short spaces of time, the beta is going to change a great deal.

So, if you're going to change the spreadsheets and use these spreadsheets and use these online resources, you don't really have to change your beta too often. If you're going to use the online resources and download them. And if you're using five year or three year beta, but if you're using very short term beta, obviously you're going to have to update this a lot more often.

So, if you're using three month, six month or one year beta, then you are going to have to update them. But I wouldn't worry about it too much. If you're using three and five year, you can update these every six to 12 months.

Now, the other thing with beta, when you're calculating your beta, when you're calculating your own beta, you can update these every six to 12 months.

Now, the other thing with beta, when you're calculating your own beta is that it's actually a step further from really what a retail trader should massively do. be worrying about because what you really should be worrying about is the positions that you've got on.

Now the other thing with beta, when you're calculating your own beta, is that it's actually a step further from really what a retail trader should massively be worrying about.

Because what you really should be worrying about is the positions that you've got on and having the correct positions. That's first and foremost.

This really comes secondary and one of the reasons why we're showing you this is because a lot of people will have the objective of working in the industry one day.

So either working for a hedge fund or working at an investment bank.

This is another thing that you'd be expected to know and understand and be able to calculate if you were going into the industry.

From a retail trader perspective, if you can actually just get the beta, and because beta isn't a perfect measure anyway.

If you can get the beta and you're trying to hedge out market risk as accurately as possible, but we all know that it can't be 100% accurate.

Because relying on beta or relying on it to be 100% accurate doesn't really work.

Beta is just a measure that we use in an attempt to try and hedge out market risk as best as we possibly can.

And beta can change. But if you use it over long enough time periods, it should be fairly accurate.

So don't worry about it too much if you're watching Chris on the computer and you think it's a bit too advanced for you.

If you can get the beta numbers, that's fine. If your objective is to work in the industry one day, then this is something you'll have to learn.

So let's go over to the computer screen. Chris is going to show you how to do it.

You've got the downloads with five year rolling beta in the download section for beta.

And you can actually go and get this number on decent websites anywhere online.

So let's go over to the presentation. Chris will show you how to do it.

And I'll see you at the end of the video with a summary of everything that we've learned so far.

Okay, so now Chris is going to show you how you can calculate your own beta in case you can't actually get beta publicly from the websites that we usually look at.

Or you think the beta data is unreliable.

So we're going to use a very well known stock in the United States and Chris is going to show you how to do that now.

So let's calculate the beta. Take it away, Chris.

In this video, I'm going to talk you through how you can calculate your own beta value using Excel.

So beta value is just a statistical measure of the sensitivity of a stock to the market.

And by market, what we typically mean as industry practice to use the index in which the stock that we're looking at is listed in.

So in this example, we're going to use Heinz as our stock, a consumer staple stock that we'd expect to have low sensitivity to the market.

And we will see how its returns correlate with the S&P 500, which is the index in which it's listed in.

And from that, we can obtain its sensitivity, which is its beta value.

So let's go ahead and get started.

The first thing we need to do is gather our data.

So if we go to Yahoo Finance and in the ticker box, the enter symbol box in the top left, we type HNZ for Heinz.

And select Heinz Company.

And then on the left hand side, navigate to historical prices.

Now we're going to calculate a three year beta, which is quite typical on websites such as Bloomberg and other financial websites.

They typically give you around a three to five year rolling beta.

So we'll obtain our data from the 3rd of March 2010 to the 3rd of March 2013.

And we'll get it on a weekly basis.

Update the table by clicking Get Prices.

Scroll to the bottom of the web page and click Download to Spreadsheet.

And at this point you can save this file on your hard drive or you can go ahead and open the Excel spreadsheet straight away as we're going to do and then save it once you're in it.

Okay, so we'll just go to File, Save As, Save it on Desktop, Save as HNZ Beta, Save it as an Excel workbook.

That's fine.

So the first thing we'll do in this spreadsheet is just adjust the Dates column so we can see all the dates.

Okay, so to calculate beta we also need the price data from the S&P 500 so we can create returns columns for both HNZ and the S&P 500 and see how they're correlated.

So if we go back to Yahoo Finance and type in S&P and select the S&P 500 from the drop down list and again go to Historical Prices.

And we need to make sure that we select the data between the same range and with the same frequency as we did before.

So that was March the 3rd, 2010 to March the 3rd, 2013 on a weekly basis.

Make sure you update the table by clicking Get Prices.

Scroll to the bottom of the web page and click Download to Spreadsheet again.

And we'll just go ahead and open this spreadsheet.

You don't need to save this file.

Okay, so now we've got our original sheet which is the HNZ price values and this is our S&P 500 prices.

So if we go back to the HNZ sheet and what we're going to do is get rid of all these columns of data that we don't need to calculate returns and our beta value.

So what we'll do is just leave the close column and the date column.

So if we select column B and hold CTRL and select C, D, F and G.

So that will select the open high, low, volume and adjusted close.

And then right click within the selection and press delete.

And that will leave us just with the date in column A and closing prices of HNZ in column B.

And the next thing we want to do is import the S&P 500 closing prices into this spreadsheet, into column C.

So what we do is go back to the S&P 500 spreadsheet and we select column E and we just press CTRL C once that's selected to copy.

And then back in the HNZ spreadsheet go to cell C1 and press CTRL V to paste.

Okay.

So to make this a little bit clearer what we'll do is rename column B and C instead of just close we'll rename them to their appropriate asset names.

So in B1, cell B1 we'll rename that as HNZ price and in, actually to make this consistent, price brackets HNZ and in C1 price brackets S&P.

And adjust the columns as necessary, the widths so we can fit all that in.

Okay.

So in column D what we'll do is create the returns for HNZ over this period.

So let's head up that column in D1.

Actually we'll do it in column E.

In E1 we'll put returns brackets HNZ, adjust the column.

And in F we'll do something similar but with the S&P so we type in returns S&P into that cell.

Now, we need to use the returns formula in cell E2 and F2.

So in E2, it's the closing price of the current day minus the closing price of the previous day divided by the closing price of the previous day.

And that gives us our return.

And we can copy that formula down easily by navigating to the bottom of the spreadsheet.

If we click on this data in column A, B and C, we can press CTRL and down to go down to the bottom of that data quickly.

We'll go across to column E and press CTRL and up to select all the cells that we want to copy down the formula in cell E2 down to.

So we've got all those cells selected.

We just press CTRL and that copies all of the returns down.

And we'll do the same thing for the S&P.

So, equals the closing price today minus the closing price yesterday divided by the closing price yesterday gives us the returns today.

And the same thing, we'll navigate to the bottom of the spreadsheet.

CTRL and shift up to select all cells and CTRL and D to copy all of that down.

So, if we just go down to the bottom of the spreadsheet, what we'll see is there's two cells there at the bottom that have got errors.

This is because our returns formula requires price data from a previous day.

And obviously in the bottom row, there is no previous day.

So, that's giving us an error.

So, what we do is we just delete those two cells by selecting them and pressing delete on the keyboard.

Okay, so, now we've got our returns.

We'll just actually make this look a bit better by selecting all our returns in the Hines and S&P column.

So, I used CTRL, SHIFT starting from cell E2.

I used CTRL, SHIFT, right arrow and down arrow to select all that quickly.

With all that selected, right click inside the selection.

Go to format cells.

And we're going to change the number category to percentage.

Two decimal places is fine.

Okay.

So, in the next step, we're going to calculate beta.

To do this, we need to use the data analysis tool, which is located in the data tab on the right hand side, over here.

If you don't already have that there installed on your Excel, you'll have to install it manually using a plugin called analysis tool pack.

And there's a guide on how you do that in the accompanying PDF.

So, let's just go ahead and click data analysis.

And we go to regression.

Select regression, press ok.

So, regression is just a statistical procedure that we use to measure how well certain variables in a model can explain another variable that we're testing.

So, that also allows us to gain sensitivity measures of each of these variables.

And that's essentially what beta is.

So, to perhaps put that to make a bit more sense in what we're actually doing here.

We're testing Heinz.

Heinz is our variable.

And we're testing it with a model of the S&P.

So, we're testing how well the returns in the S&P explain the returns in Heinz.

And by comparing those, by modelling that, it will show us the coefficient, which is the sensitivity of the S&P 500.

Sorry, it will give us a coefficient of the S&P 500 that shows us the sensitivity of Heinz to the S&P 500.

Ok, so let's just continue.

If you want to know a bit more about regression, it is explained a little bit more in the accompanying PDF.

And also, there's plenty of resources online that you can look at as well.

But let's just go ahead and start.

So, our Y input range is our Heinz return.

So, in the Y input range box, we'll click cell E2 and press CTRL-SHIFT and down.

And that will select all the Heinz returns.

And then we click into the X input range box and do the same for the S&P.

So, we click F2, cell F2, CTRL-SHIFT down to select all of those cells.

And we want to display our regression in this spreadsheet.

So, we change the output range from a new worksheet to output range.

And be careful, because this throws our selection back up to the Y input range, which we've already selected.

And we don't want to edit that.

So, make sure you click off into the output range box.

And we're going to display this in cell I2.

And just before we press OK and display our regression, we need to make sure that we click the line fit plots box down here.

Which will show us a graphical interpretation of our regression.

So, just select that and press OK.

OK, so just before we edit this data a bit, let's just, or just before we look at this data and I explain it a bit more, let's just edit these columns so that they show all this data properly.

So, with all that still selected, we'll just go to home on the ribbon.

And then format and then auto fit column width.

And that allows us to see all this data a little bit more easily.

And now we'll edit the graph before I finish up by summarising what we're actually looking at here.

So, just make the graph bigger by clicking and dragging the bottom right of the graph.

OK.

So, there's a few things we need to do here.

The first thing, we'll edit the name of the graph.

So, instead of x variable one line fit plot, we'll call this Heinz beta.

We don't need these labels here on the right hand side, so we just select them and press delete.

We want to be able to see our graph a little better.

So, all these dots here, what you can do is edit the size of these dots so they aren't quite as intrusive and they don't cluster quite so much, or they don't appear to cluster as much.

So, if we just select one of the blue dots, and actually click off again, and if we just double click one of the blue dots, and go to marker options, and change the marker type to built in.

Reduce this to size 4.

So we can see a little bit more about what we're dealing with.

Right, so the last thing to do, we'll rename the axis labels.

So we can see a little bit more about what we're dealing with.

Right, so the last thing to do, we'll rename the axis labels.

The axis labels.

So first, the axis labels.

Reduce the size so we can see them all a little bit better.

Reduce it to 4.

And do the same for the red dots.

So click off, and then double click one of the red dots.

Marker options.

Built in.

Reduce this to size 4.

Okay, so we can see a little bit more about what we're dealing with.

Right, so the last thing to do, we'll rename the axis labels.

So first, the x-axis is the S&P 500.

And the y-axis is Heinz.

Okay, and we'll move these by clicking and dragging those labels.

So it makes a bit more sense.

Okay, so this axis, horizontal axis, represents the S&P 500 returns in relation to the y-axis, which is the Heinz returns.

And all these dots show, for a given week, what the returns in Heinz were compared to the S&P 500.

And what we can see is that the S&P 500 generally increases at a higher rate, a lot higher rate, than the Heinz returns.

So let me just demonstrate that.

If you were to just eyeball this and look across from 5% return on Heinz, and go across.

Okay, 5% on S&P would be roughly here.

And none of our actual values are there.

Okay, so what that's saying is that the S&P returns, for Heinz to have a return of 5%, the S&P returns would generally be a lot higher.

So, tipping that on its head, what we can say is, compared to the S&P 500, Heinz returns a lot less, given a movement in the S&P 500.

So, the sensitivity of Heinz to the market, to the S&P 500, is low.

And that's what we'd expect, because this is a consumer discretionary, sorry, a consumer staple stock.

Meaning that it's less affected by the business cycle.

There's always some demand, and so it has fairly consistent returns.

It's a defensive stock.

Okay, so that's the graph explained a bit.

So, I explained what the blue dots are.

They're all the individual returns of Heinz versus the S&P 500.

The red dots are, basically represent a line of best fit between all the blue dots.

Okay, so that's like our model line.

And the slope of that line represents the sensitivity of Heinz to the S&P 500.

And so the slope of that line is also our beta value.

And we're given the slope of that line in this data summary output.

X variable 1 coefficient, so that's cell J19, that's our beta value.

So our beta value is 0.38, roughly, of Heinz.

Which makes sense, again, it's a defensive stock.

So, I'm going to hand back to Anton now, who's going to talk a bit more about what we've discussed here.

And give a short summary on how you can use beta, why it's useful and why we've done what we've done here today.

Okay, welcome back.

So, what you just saw there from Chris was really a step-by-step guide to calculating your own beta.

You can actually go into the downloads section and we've got a PDF there, which takes you through the entire step-by-step process to calculate your own beta.

As I said earlier, you don't really need to go and do this for everything you do.

If you do actually manage to get, you know, accurate beta online and you've got a good resource for getting a beta that has a decent time length, you shouldn't worry about this too much.

You definitely do not have to do this step-by-step for every single position you've got in your portfolio.

That's just crazy.

I think, from a retail trader perspective, the most important thing is that you've got the right positions and then you attempt as best as possible to hedge out market risk if you want to go and do that.

Remember, you can actually be cash for cash, as in long $10,000, short $10,000.

But if the betas are wildly different and the beta ratio is high, that cash for cash is not going to work very well as a trade.

So, you may want to try and hedge out as much market risk as possible.

So, the step-by-step guide is there.

You can always refer back to the video if you have some difficulties and watch Chris go through that process again.

But, you know, definitely don't do this for every single trade that you do.

That would just be doing too much work for no real value add to your portfolio if you can get the beta somewhere else.

The other thing that we've mentioned, you know, in terms of this process, if you are of the objective that you're going to work in the industry one day, you want to work at an investment bank, you want to work at a hedge fund, then this is actually quite important.

You do actually have to understand this.

If you are working at an investment bank and a hedge fund for that matter, you would be looking at your own portfolio and you would be looking at what we call a value at risk.

So, the amount of money that your portfolio can make or lose per day on a one standard deviation, two standard deviation and three standard deviation day.

And there's a lot of assumptions made by the back office and middle office in terms of the betas that they input into your portfolio.

So, you'd actually have to understand this process so you know when you're looking at your portfolio what the real situation is in terms of the value of money at risk that you can make or lose per day.

So, if your objective is this, you should, to work in the industry, you should absolutely learn this inside out.

From a retail trader perspective, don't worry about it too much.

You can go cash for cash.

If the beta ratio is high, you will attempt to hedge out market risk as best as you possibly can.

If you can get the beta publicly from a decent website, then that's fine.

If you can't find beta anywhere, then try and go through this exercise.

Okay.

So, now we're pretty much done with risk management processes.

But, the last thing we have to do as a trader in terms of having discipline is having self-awareness.

Self-awareness of our own abilities as traders.

So, that's what we're going to do next.

We're going to go over to video number 25 and start looking at some standard industry metrics that measure your performance as a trader.

So, you understand where your weaknesses are and where your strengths are and what you need to work on over the medium to long term as a trader in terms of your weaknesses.

So, let's go over to video 25 where we'll be looking at the Kelly criteria.

Thank you.
