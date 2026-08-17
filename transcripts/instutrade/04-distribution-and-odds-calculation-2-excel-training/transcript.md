---
course: instutrade
lesson_id: "04"
title: "Distribution and Odds Calculation 2, Excel Training"
module: distribution-and-odds
module_title: "Distribution and odds calculation"
duration: 00:50:04
duration_seconds: 3003.808
source: "Anton Kreil - Professional Trading Masterclass Instutrade/4. Distribution and Odds Calculation 2, Excel Training.mp4"
model: "ggml-large-v3-turbo.bin"
related_documents:
  []
---

# 04 — Distribution and Odds Calculation 2, Excel Training

Okay, so now we're going to go over to Christopher Quill. Chris is now going to show you on the computer how you calculate your distributions for initially the S&P 500, but you can use this for any asset. So take it away, Chris.

So in this example, we're going to look at a day trading strategy for the S&P 500 over a period of roughly 50 years. By calculating these daily returns, we should get a good idea of how the S&P 500 the underlying asset behaves behaves on a daily basis. So we're going to start by going to Yahoo Finance and obtaining the data. So finance.yahoo.com. And then in the ticker box, we type S&P and we select the first drop down item, S&P 500. And this gives us a summary phrase page of the S&P 500 with Yahoo Finance's last available price for the asset. But we're going to go to historical prices on the left hand side and update the historical price table by editing the inputs given at the top here. So we're looking for data from between the 3rd of January 1962 to the 9th of November 2012 on a daily frequency.

So once we've set our parameters, we update the table by clicking Get Prices and we scroll to the bottom of the page and click Download to Spreadsheet.

At this stage, you can select to save the spreadsheet to your hard drive. Or as we're going to do, you can just open the spreadsheet straight away and save it once it's open.

With the spreadsheet open, we're just going to go to File, Save As. We're going to save it as S&P 500 Returns Distribution.

And we'll save it as an Excel workbook. And I'm going to save it on my desktop so it's easy to find.

So the first thing that we're going to do is adjust this date column so we can see the dates.

So we just click on the column intersection and adjust the width of the column like that by clicking and dragging.

So this is all the price data for the S&P 500 from the daily price data from the period that we've selected.

So in our example, we're only going to use the open and closing prices to calculate daily returns.

So let's go ahead and do that by heading up column H with returns in cell H1.

And then in H2, type our returns formula, which is brackets, closing price for that day minus the opening price for that day, divided by the opening price, which gets it in terms of a percentage return for that day.

And then we want to apply the formula that we've just put into cell H2 down the whole returns column.

So a quick way to do that is click anywhere in the data from column A to G.

So cell G2, for example, and press CTRL and down to navigate quickly to the bottom of the spreadsheet.

And then find the last cell in column H.

So that is H12804.

And then we press CTRL, shift and up to quickly select all the return cells that we want to implement our formula into.

And then with that selected, we just press CTRL, D to copy that formula down from cell H2 to the rest of the column.

So now we've got our returns, we want to be able to analyse them and interpret them in terms of a distribution.

So by that I mean we want to be able to understand how many of these daily returns, S&P 500 daily returns, lie within specific ranges that we set.

And we're going to set those ranges by creating intervals in the data.

So in column J, cell J1, head up the column with intervals.

Okay.

And then what we want to do is come up with a reasonable set of intervals for trading the S&P 500 daily.

So a lower bound for the ranges we're interested in might be minus 2%, for example, because we're only looking at daily data.

So looking at anything with too wider range would be pointless because it wouldn't really show us the core of our data set.

So we'll start with minus 2%, so minus 0.02, we enter into cell J2.

And then we'll go up in increments of half a percent.

So in the next cell, J3, we type 0.0.015, press enter.

And to quickly use this interval that we've set and copy it down to an upper bound of plus 2%, we select those two cells, J2 and J3, and then select the small black box in the bottom right-hand corner of the selection and drag it down to cell J10, which gives us plus 0.02, which is plus 2%.

So we're going to use these intervals to create a distribution table to see the frequency of our daily returns that land within these intervals.

So to do that, we have to go to data on the ribbon and data analysis on the right-hand side.

If you don't have this at this point, there's a guide of how you obtain this data analysis option in the accompanying PDF.

And you do it by installing an add-in to Excel called Analysis Toolpack.

So we go ahead and click on Data Analysis.

And we want to create a histogram data.

So that's basically a frequency table.

And press OK.

And we're going to create this table from our returns data.

So we select in the input range, cell H2, and press Ctrl-Shift and down to quickly select that whole returns column.

The bin range is just the intervals that we want to define our ranges with, that we're interested in interpreting our returns within.

So our bin range is just our intervals that we created in column J, from J2, Ctrl-Shift down, select to J10.

Now, we want to display this histogram data in this spreadsheet that we're working in, rather than a new worksheet.

So in output options, we select output range, and you can see this throws you back to the input range box, which we've already filled in with our returns data.

So we need to be careful to click off that into output range and select whereabouts in the spreadsheet we want this frequency table to be.

So we're going to use cell L2, and we're going to use cell L2, and so we click L2 and press OK, and that gives us a tabular format of a histogram.

So basically, a frequency table, and what this essentially means is, if we take the first row, for example, in this table, this means that 285 days, the S&P 500 yields a return of less than or equal to minus 2%.

And the next row, and the next row, 345 days, yields a return of between minus 2% and minus 1.5%.

OK, and that's how the table works.

So if you go to the bottom, eventually you get to 307 days, lie greater than 2%.

OK, so what would be useful is if we interpreted this data visually, so we create a graph from this data.

So to do that, we just select the data, L3, click and drag to M12 to select that data, and go to Insert on the ribbon, Column, and the first 2D Column Chart option.

Click that, and that gives us a histogram of our data.

OK, so at the moment, what we can see is that clearly more returns on our distribution lie close to zero.

OK, so that's what we can tell so far, and that a lot less, it sort of tails off, and it looks something like a bell-shaped curve, a bit like a, well, a lot like a normal distribution at the moment, where there's a lot less frequency of returns, where there's a lot less frequency of returns in the tails, than in the centre.

OK, so we should tidy this graph up, and make it a little bit more easy to interpret.

I'm just going to go ahead and zoom out of the spreadsheet a little bit.

To do that easily, you can just hold CTRL and then use your mouse wheel to zoom in and out of the spreadsheet.

So, we're going to replace this horizontal x-axis with some more appropriate labels, so we can understand the ranges that our frequency of data lie within.

So, to do that, let's create a range column in column N.

So, in N2, we'll type range.

And in N3, we'll type the appropriate range that applies to this bin value, and so on.

And we'll do that in all of these cells, from N3 to N12.

Before we do that, though, because we're going to type it in as text, we want to format these cells, so they know that these cells are going to be displayed as text, or understood as text.

So, we select all those cells, and right-click within the selection, and click Format Cells.

And we then want to change the category to text, and press OK.

Okay, so we'll start with the first row, and we'll call this range less than minus 2%, and then the next range will be minus 2% to minus 1.5%, and so on.

So, we're just using the bin values as a reference to complete this table, this column, rather.

So, it's a little bit tedious, but it's a good thing to do, so you can actually understand your data graphically with the correct ranges defined.

And in the last cell, in cell N12, we're going to type greater than 2%.

Okay, and let's adjust this column width, column N, so it can include all that text, and it doesn't overlap into another column.

Okay, so now we want to change the horizontal axis labels to the ranges that we've created here.

So, to do that, we click on the graph, and right-click, and select data.

And then we want to change the horizontal category axis label, and edit, so we click on edit, and we change it from these bin values, which are currently selected, to these range values instead.

And we just press OK, and OK again, and you can see that it's updated our histogram, and now we can understand what these bars actually mean, in terms of the ranges that they apply to.

Okay, so the next thing we'll do is delete this series label, so we just click on series 1 and press delete, and I suppose we want to add some axis labels to this graph, so we can understand it even better.

So, to do that, we go to chart tools layout in the ribbon, and then axis titles, and we'll label the primary horizontal axis first.

We'll choose title below axis, and that gives us axis title as the title, so we want to select that, delete it, and replace it with daily return range.

Click off it, and then the same thing to the vertical axis title, we'll choose rotated title, select it, and delete, and we'll rename it as frequency.

Okay, so that's our histogram done, so we can graphically see the frequency of daily S&P returns that lie within these ranges historically over the period that we've considered.

Okay, so I've already talked about how this distribution is much like a normal bell-shaped curve, but for those of you a little bit more familiar with the normal distribution, we can see that these bars don't tail off quite as quickly as a normal distribution would.

Basically meaning the tails are slightly fatter, that we can see visually, meaning there's more extreme values, and we'll come on, we'll sort of prove that in our data as we continue, but we can already see that this isn't quite a normal distribution.

So, we can use Excel to give us some summary statistics of our data set, and to do that we go to data, and data analysis, then we're going to choose descriptive statistics, and press ok.

And our input range is our returns column from cell H2.

Control shift down, selects the whole returns column, and we'll scroll back up to the top of the spreadsheet, and we want our output range to be on this spreadsheet, on this worksheet, so our descriptive data is on this worksheet, and so we change the output options to output range.

And then remember to click off the output range, and we're going to use cell T2 to display the descriptive statistics, and we'll need to make sure that we choose summary statistics at the bottom to display our descriptive statistics before pressing ok.

So this will load a number of summary statistics of our data, so it's done it now, we'll just adjust the column widths, so we can see this data, see these statistics a bit more easily.

Ok, so let's interpret some of these.

So the mean, this is just the average daily return of the S&P 500 over the historical period that we're looking at.

Ok, so this is about 0.03%.

Intuitively we would know it's positive, because we know the S&P 500 is up since 1962.

The median is the middle number of the data set, so if I had a data set of 1%, 2%, and 10%, the middle of that data set would be 2%, the middle number.

So that's the median.

Intuitively, by seeing the median, the middle number is above the mean, we know that more values lie above the mean than below the mean, so the ones below the mean must be more extreme.

And so we can interpret this as the negative values being more extreme than the positive ones.

Ok, so let's continue.

The standard deviation is the next one.

We can just interpret this one as a measure of the dispersion of the data.

Ok, so in a normal distribution, you might know that there's roughly 68% of the frequency of the data lies within one standard deviation either side of the mean.

So in this case that would be 1% either side of the mean.

That's not necessarily true, in fact it isn't true in our empirical distribution as we'll see further on.

So just bear in mind it's a measure of our data's dispersion.

So next we'll look at the kurtosis and skewness values.

These are just values that help us understand whether our data is normally distributed or not.

So the kurtosis value is a measure of how peaked the data is and how the tails differ from a normal distribution.

So a normal distribution in terms of how Excel displays the kurtosis value would have a value of 0.

So this high kurtosis value basically means that our data set, our empirical data set, is more peaky and has higher or fatter returns in the tails.

Ok, so fatter tails in our data set.

And the skewness value as a minus number means that basically our fat tail, our negative fat tail, is bigger than our positive tail.

Meaning that extreme negative movements are more likely to occur than extreme positive movements.

Ok, so the next value we look at is the range which is just the difference between the highest daily return that's been in our data set to the lowest daily return.

And that's split up into the maximum minimum which are the next two cells.

So we can see that the lowest daily return is minus 20% which is twice the magnitude of the largest positive return which is just 10%.

So again that backs up our idea about skewness.

Negative extremes are of greater magnitude than positive extremes.

The sum is just the sum of our entire returns column.

Effectively it means nothing other than that.

It's certainly not the return that you would yield if you held this asset from 1962 to 2012.

And finally the count is the number of trading days within our data set.

So now we've interpreted our descriptive statistics a little bit.

Let's display the frequencies of our ranges in our data in terms of probabilities so we can interpret them a bit more easily.

Ok, so in column O let's head this column with probabilities.

And in O2 we type the formula, sorry in O3 we type the formula for probabilities which is just the frequency, the number of days within this range.

So that's M3 divided by the total number of trading days, that's the count in our descriptive statistics which is U16.

And that will give us a percentage.

But before we enter this formula into this cell we're going to press F4 which puts these dollar signs around the denominator of the equation when our cursor is on the denominator.

It fixes the cell that your cursor is within and when I pressed F4 just then it fixed the denominator which basically will allow us to drag down the formula, copy the formula down to the cells below and it will just move the numerator down appropriately but it won't change this cell, the denominator.

Ok, so if we just press enter and then select that cell again and drag this formula down.

And while that's still selected if we right click within that selection and format the cells so that their percentages are displayed as percentages.

Ok, so we can see for example that 5.64% of our data, of our daily return values lie within minus 1.5 to minus 1.1%.

Ok, so that we can interpret all these probabilities like that.

So basically for this first value that would be 2.23% of our return values lie lower than minus 2% so less than or equal to minus 2%.

Another way to understand and interpret these probabilities a bit more easily is if we display them in cumulative probabilities which will allow us to analyze sections of the data.

So if we head column P, so column P, so column P, cell P2 and we put cumulative probabilities, adjust the column width appropriately.

And this time in the first cell P3 we just type equal to O3.

In cell P4 we type equal to P3 plus O4 and then we can copy this formula down in cell P4 and this will give us our cumulative probability distribution.

Ok, so what is meaning when we can interpret this a bit better than our normal probabilities column is because we can start saying things like 10.56% of the data lies with the return of less than minus 1%.

Ok, so 10.5% of the time the S&P 500 yields returns of less than minus 1%.

And you can turn that on its head and say that 90% of the time the S&P 500 yields a return of greater than minus 1%.

So you can kind of interpret these how you like and manipulate it how you like.

Ok, so let's go ahead and tidy the spreadsheet up a little bit now.

If we just tidy these values up that we've just been looking at, we'll create borders around these cells.

So if we select cell L2 down to P12 and then go to the home tab on the ribbon and with this range still selected, go to the borders drop down and select all borders.

That will give borders around those cells and we'll move the graph to the right hand side.

So let's zoom out the spreadsheet, move the graph to the right hand side before we continue.

So our spreadsheet looks a little better.

Ok, so we've basically done, considered some basic statistics and got a basic understanding of how our distribution works using the tools that Excel has given us so far.

But what we can do is manipulate this data further to get a real in-depth understanding of what's going on.

And we'll do that by filtering the returns column and then analysing subsets of data.

So before we continue, let's add three rows to the top of the spreadsheet to create a little bit more space.

So we just click on row 1 on the left hand side and right click, click insert, 1, 2 and 3.

And then what we can do is, once we've filtered these returns, we'll look at the average of a subset.

So first of all, let's add the filter to the returns column.

Ok, so we click on cell H4, the top of the returns column, and go to data, the data tab on the ribbon, and select filter.

And this is applied drop down arrows to all the columns here, A to H, which allows us to filter and sort all these columns by any of these date, open, high, low, returns, whatever, any of those.

So for example, we could change all this data from newest to oldest to oldest in terms of date.

So that's turned the dates now upside down.

So now we've got the return, the close, the open, all of that data for 1962 at the top.

Ok, so we'll just go and undo that, change it back to newest to oldest.

So now we know we can filter our returns.

What we'll start by doing is working out the average of subsets of returns.

So to do that we need to create a cell that works out the average of this returns column when it's filtered and sorted and we've done whatever we want to.

So in cell K2, let's type average return and adjust the column width.

And in L2, we type the formula to work out the average return for the subset, which is subtotal, brackets, one for the average, comma, the reference values, which are the returns column, which is now H5, down to H12807.

And then we close the brackets in the formula bar up here and press enter.

Ok, and that's given us in L2 the average return for our entire unfiltered data set, which you'll notice is obviously the same as our mean as a data set because average and mean are the same thing.

It's displayed slightly differently because of rounding, but they are the same values.

But what will happen is when we change the returns column, this average return will change here, but the mean, the descriptive statistics, these are all fixed from our total data set, so these won't change.

Ok, so what might be useful is if we understand the average positive and negative returns of our data set.

Ok, so to do that we filter the returns column, so we click on this filter here, number filters, and what we're going to do is go to greater than to filter them.

We put greater than zero and that will give us only positive returns.

Ok, so that's unfiltered.

Ok, so before we continue actually, let's just name cell M1 avpos for average positive return and M2 avneg for average negative return.

Ok, and as you notice when I filtered those returns it actually hid a load of rows because it's taken out all the zeros and negative return values.

So for example we go from row 5 to 8 and it's affected the rest of our spreadsheet, but don't worry, when you clear the filter in the returns column that will all go back to normal.

What you also will notice is the average return in cell L2 has changed to the average return for all positive returns.

So what we can do, because this keeps changing to our average return for whatever we display, whatever we filter, we'll copy this by right clicking on the cell, copy, and we'll paste it into N1 representing the average positive return as a value which is fixed and so won't change.

And we can do the same for negative, so we go to number filters in the returns column, less than zero, ok.

And now we've got the average negative return in L2, again we're going to copy that and we're going to paste it as a value into cell N2.

Ok, so what we can do now is calculate the number of days that the S&P 500 has been up and down and calculate that as a percentage of the total days that we've got in our data set as well.

So before we continue, we need to create a cell that can do a similar thing to this average return, but just for count, so it just counts the subset of return data.

Ok, so in, actually before we continue we'll just unfilter this returns column.

Ok, and then in cell T2 what we'll do is create a cell called count and then in U2 we'll type in the formula for typing the count of the subset of returns.

So that will be subtotal, similar to before, similar to the average return, brackets 2 this time for count, you can see that from the drop down menu here.

And then comma, the reference numbers which are the returns column, so that's H5, press control shift down, select the whole returns column, close the brackets, press enter.

Ok, so that's created the count for our subset of data, for our unfiltered data because we removed the filter beforehand.

And we can verify that because it's the same as our descriptive statistics count down here.

And this will change when we change our filter.

So, let's add another column to the top of the spreadsheet.

And type frequency into cell O1.

And frequency percent into P1.

And then, what we'll do is work out the number of days that the S&P 500 has been positive in our data set.

So let's filter the returns again to positive, number filters, greater than 0.

Ok.

This has changed the count to 6707.

So we just put in that, 6707.

You can copy and paste in with the values like I did before or just type it because it's quite easy this time.

Ok.

And the same for negative, so less than this time.

Less than 0.

Ok.

And this is 6006 days.

So obviously that's going to be missing some days because there will be some days that are 0.

So let's count those as well.

So in cell N4, we'll add 0 as a value and work out the frequency of that by filtering the returns column to equals 0.

Ok.

And we've got a count of 90.

So we'll just put in 90 in cell O4.

Ok.

So clear the filter from returns.

So as a percentage, to work out the percentage of a number of days that are positive, negative and 0.

So for positive in P2, we type equals O2 divided by U20.

So that is the number of positive days in our dataset divided by the total number of days.

And we'll fix cell U20 so we can copy down this formula again.

Ok.

So we can copy this down.

And with this still selected, we'll right click within the selection format cells and change that percentage to a percentage with two decimal places.

Ok.

So we can see now 52% of our days the S&P 500 has yielded positive return, 46.9, negative and almost or close to 1% it's flat.

So what we can do now is we're going to work out the average return if you were to predict when the S&P 500 is up and you go long on all those days.

You work out the average daily return that you'd get over this entire period.

Ok.

So if we type average return and then in cell Q2 we type equals this average positive return times by the frequency.

Press enter and we do the same.

We can copy that down to the negative cell.

So we've got the average negative and average positive return.

Should you, so I'll explain that a little better.

So this cell Q2, this refers to the average positive daily return that you would get if you predicted all the days when the S&P 500 would be up and you invested in those.

And you were flat all the other days in this entire period.

Your average return per day would be this.

And the same for negative.

Ok.

So let's just change all these to percentage values now.

So cell N2 and N3 select them.

Format cells.

Right click in the selection.

Format cells.

Change the percentage.

Two decimal places.

And the same for these average returns here.

So what this is telling us, these average returns are that even if you predict the positives and invest in only those days and go flat the rest of the time or don't invest the rest of the time, the margins, the profit margins you work with are still pretty small.

Ok.

And because we're trading daily and these are our sort of average returns that we get daily even if we predicted it right, they're going to get wiped out by things like transaction costs.

They're not, it's almost not worth trading daily when you have this, when you have a normal amount of volatility.

Ok.

So that's what these values here are telling us.

The final procedure that we're going to carry out on this spreadsheet is to find out how many trading days lie within different standard deviations of the mean in our data set.

Ok.

So what we need to do is, in fact first we'll clear some space on the spreadsheet.

So if we just add another two columns into the spreadsheet.

And what we're going to do is calculate the standard deviation returns values for one, two and three standard deviations above and below the mean.

Ok.

Ok.

So in cell W2 type std dev standard deviation and one, two and three in x, two, y, two and z, two respectively.

And then upper that represents the one standard deviation, one, two and three standard deviations above the mean.

And then another row lower for one, two and three standard deviations below the mean.

So that was in cell W3 and cell W4.

Ok.

So to work out these values, these return values, what we do, in cell X3 we'll type equals the mean.

Ok.

So we always start with the mean.

And then for one standard deviation above the mean, because we're in the upper bound, we just plus the standard deviation.

Ok.

And for the lower bound, we start with the mean and we minus one standard deviation.

Ok.

In the next column, we're applying that method to two standard deviations.

So we start with the mean and we add two times the standard deviation.

And for the lower bound, we start with the mean and we minus two times the standard deviation.

And the same for the last column.

So equals the mean plus three times the standard deviation.

And the mean minus three times the standard deviation.

Okay.

So now we've got the returns values that represent one, two and three standard deviations above and below the mean.

So for now, we're going to keep these as decimal displays because we need to input them into our return filters.

Sorry.

Return filters over here in a minute.

Okay.

So we're going to find how many trading days lie between yield returns between these values.

Okay.

So we'll find out how many trading days in our empirical distribution lie between roughly that's plus one percent and minus one percent, which is one standard deviation.

And then we'll do the same for two standard deviations and three standard deviations.

And we'll compare it to how many days a normal distribution would give us with those standard deviations.

Okay.

So in AB2, cell AB2, we'll type standard deviation again.

And this time one, two and three going down the column.

And then we type actual.

So this will be that column for the actual number of days in our empirical distribution that lie between these bounds for one, two and three standard deviations.

Okay.

And we'll compare that to what a normal distribution would be.

And then we'll compare the percentage of these values as well.

Okay.

So that's AC3 is actual, AD3 normal, AE3 actual percent, and AF3 normal percent.

So let's filter our returns column.

I'm just going to zoom out the spreadsheet a little bit.

Filter our returns column between these standard deviation returns values.

So if we click the filter on the returns column and we go to between, we want to give returns that are greater than or equal to our lower bound for one standard deviation.

So that's this value here.

So we can type in minus 0.00972 and less than our upper bound, which is 0.01031.

Press okay.

Filter that.

We see we've got 10,062 days that lie within those values.

So we just input that into cell AC3, 10,062.

Okay.

And we do the same for the two standard deviations.

So filter between.

This time we're using these upper and lower bounds.

So below, sorry, greater than 0.01974 and less than 0.02032.

Filter.

So that's 12,208.

You can see that in cell U5.

That's the count that changes with our subset of returns.

So 12,208.

And we'll do the same for the three standard deviations.

Minus 0.02975 and 0.03033.

So we put that in here.

Okay.

So let's go to the normal distribution now.

And we're going to start from what we know about our normal distribution is we know the percent of the frequencies, the percentage trading days that should lie between one standard deviation from the mean and two and three.

Okay.

So in a normal distribution, 68.2 percent of trading days will lie within one standard deviation from the mean. 95.4 percent of trading days will lie within two standard deviations from the mean in terms of their returns.

And within three standard deviations from the mean, 99.8 percent of trading days will occur.

Okay.

So let's fill out the actual number of days given our total count. 12,803 days in our data set.

We can work out the normal number of days that is the number of days predicted by a normal distribution that would lie within one, two and three standard deviations.

So that's just in AD3 we type equals the percent that would lie within one standard deviation times the count.

And we'll fix the count cell.

Press F4 around U22.

And then we can apply this down.

And we can see that we've got 12,777 days that a normal distribution predicts will lie within three standard deviations from the mean.

Okay.

Given a data set of 12,803 days.

So let's just convert these actual days to percent as well.

So this is the actual number of days within each standard deviation from the mean divided by the count.

Okay.

So AC3 divided by the count.

We'll fix this cell again as a reference so we can copy it down.

Copy this down.

And with that still selected we'll format these cells as well.

I'll display them in a percentage.

Okay.

So.

I think before we interpret these last results let's select the cells X3 to Z4 and change all these standard deviations to in terms of percent as well.

With two decimal places is fine.

Right.

So.

Let's do these first.

So.

Our standard deviations.

One standard deviation from the mean represents roughly an upper bound of one percent and a lower bound of minus one percent.

Okay.

Which means two standard deviations will be roughly that.

Roughly two.

Times that.

And three.

Three times that.

So.

In terms of where these standard deviation values lie on this histogram.

We're looking at an upper bound of one percent and a lower bound of minus one percent.

So we're looking at from this bar here to this bar here is one standard deviation.

Okay.

Which in our empirical distribution accounts for almost 80 percent of our data.

Whereas in a normal distribution it's something like 60, 68, ten percent lower.

This means that our empirical distribution there's many more trading days that lie closer to the mean.

Okay.

Which is close to zero as well.

We should point out it's close to zero.

So that means our distribution is more peaked.

Which is predicted by our kurtosis value that we discussed earlier.

It's more peaked than a normal distribution.

Okay.

And as we go further out and we look at the standard deviations that are deeper into the tails of the distribution.

We can see that instead of our empirical distribution accounting for more than the normal distribution.

It starts accounting for less.

By the time we get to three standard deviations our empirical distribution accounts for 98.7.

Whereas the normal distribution accounts for a percent more.

As you go further and further out this difference will be more significant.

So basically what we're saying is our empirical asset distributions tend to have fatter tails.

More extreme movements than predicted by normality.

Okay.

So what does this all mean?

Okay.

So two key things.

Okay.

First thing.

The fact that 80% of the time the S&P barely moves makes it a lot harder to generate returns.

Okay.

Especially when you account for transaction costs.

It means that our opportunities are minimal when we're looking at daily trading.

Especially when the volatility's are low.

Okay.

And that's given by these average returns that we looked at over here as well.

The second thing is.

Just something to be aware of.

Is that by analyzing this distribution of returns we can understand that there are greater risks in the tails.

In the extremities of the distribution.

So they're actually more probable than you might think.

Okay.

So that means there are likely to be days when you'd be wiped out of your position.

Of your account.

Okay.

So roughly one in a hundred days we've got a fairly significant move of more than 3%.

Which could wipe you out if you've got the position on the wrong way.

Okay.

So they're the two major things.

So the key thing we need to understand is that this basically implies that opportunities are minimal when there's low volatility.

The other thing just to keep in the back of your mind is that there is greater risk than predicted by normal distributions.

And we should also point out that this spreadsheet, you can apply this method to any asset over any period, any frequency.

So one week, like weekly, monthly, yearly data.
