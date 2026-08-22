---
course: instutrade
lesson_id: "19b"
title: "Video 19 Supplement; PEG Ratio"
module: drilling-top-down
module_title: "Drilling from the top down"
duration: 00:21:08
duration_seconds: 1268.16
source: "Anton Kreil - Professional Trading Masterclass Instutrade/19b. Video 19 Supplement; PEG Ratio.mp4"
model: "ggml-large-v3-turbo.bin"
related_documents:
  []
---

# 19b — Video 19 Supplement; PEG Ratio

In this video I'm going to cover the price earnings to growth ratio, or PEG ratio as it's sometimes known, and talk about how it can be used effectively in the investment process, and illustrate some arguments as to why we use it in this way, using a couple of Excel examples.

So this material is basically supplementary to video 19, drilling from the top down 2, where we discuss similar things with the PE ratio.

So what is it? The PEG ratio is just a valuation multiple that builds upon the standard PE ratio, and it aims to improve upon it by accounting for a company's anticipated growth in earnings.

Now the reason why this can be regarded as an improvement comes down to financial theory, which says we can value something by discounting its future cash flows, and to anticipate future cash flows we need to be able to forecast a growth rate, and that's the principle behind models like the DCF model.

So the reason why I'm covering the PEG ratio in this video is that it's becoming a much more widely used valuation metric, and it's important that we as retail traders know how to deal with it correctly.

So as far as calculating the PEG ratio goes, it's fairly simple. It's just the PE ratio divided by the earnings per share growth.

So for example, if we have a PE ratio of 10 and annual growth in earnings of 20%, then the PEG ratio is just 10 divided by 20, which equals 0.5.

Now, theoretical finance teaches us that a stock with a PEG ratio of less than 1 is undervalued or cheap, and conversely, a stock with a PEG of over 1 is overvalued or expensive.

And sometimes you might see analysts in the market justify their stock recommendations in this manner, for example, by putting a buy recommendation on a stock with a PEG ratio of less than 1.

But this is the wrong way to deal with the PEG ratio in the investment process, and it's the same trap that retail investors often fall into.

So in reality, the PEG ratio is as misinterpreted as the PE ratio, and all it actually represents is the price the market is willing to buy and sell the company's earnings and earnings growth potential for.

So just as in the PE ratio, there's no cheap or expensive, under or overvalued, and similarly to the PE ratio, the PEG ratio can stay the same while the stock price rises or falls.

So if we take an example of that, stock A is trading at $10 a share and has a current earnings per share estimate of $1 and growth in earnings per share estimate of 20%.

So our PEG ratio there is just the PE ratio divided by the earnings per share growth, which is 10 over 20, which is 0.5.

Now, we can also figure out last year's earnings per share by discounting this year's expected earnings per share estimate and the expected earnings per share growth.

So that's simply obtained by taking the earnings per share $1 divided by the discount factor of 1.2, which equates to the 20% EPS growth figure, and that equals $0.833.

So now, if we imagine that the company comes out and guides the market down to a revised lower EPS number of $0.9, then this effectively changes the EPS growth rate to 8%, which we can figure out using last year's EPS number.

So with the EPS number and EPS growth figure revised down, all that has to happen for the PEG ratio to remain constant at 0.5 is for the price to fall proportionally.

So in this case, the price just needs to fall to $3.6.

So as long as the stock price falls proportionally with the earnings and the earnings growth relative to the previous year, then the stock can lose almost all its value, while the PEG ratio actually remains the same.

So in this case, theoretical finance would actually tell us to buy this cheap stock all the way down from $10 to $3.6, and we would have lost a lot of money doing so.

Now, in reality, the stock price actually anticipates moves in EPS and EPS growth numbers in terms of the PEG ratio.

So for stocks with a PEG ratio of less than 1, they're actually punished by the market for continually missing EPS and EPS growth estimates, and therefore, the market expects them to miss them again and again.

And it's prepared to sell the stock at a low valuation because they regard the company's earnings a low quality.

And in the future, what's actually likely to happen is that the EPS and EPS growth numbers will catch up with the stock price.

And if you argue with this and actually buy the stock, you're claiming that essentially you know more than the market when you don't.

And similarly, with stocks with a PEG ratio of over 1, they're rewarded by the market for continually beating EPS and EPS growth estimates.

So the market expects them to beat them again and again and is prepared to buy the stock, this time at a high valuation, because the earnings and growth are of high quality.

And again, in the future, it's likely that the EPS and EPS growth numbers will actually catch up to the rising stock price.

And if you argue with that and short the stock, again, you're claiming that you know more than the market and quite often you'll end up being proved wrong with a hefty loss to your trading account to go with it.

So the fact that the market is willing to pay more for quality earnings drives us to the same conclusion as in video 19, where we showed that nothing is ever cheap or expensive.

So we've basically seen that share prices can go from zero to infinity and vice versa, while the PEG ratio actually remains the same.

And so the most important thing to take away from this video is the understanding that the PEG ratio is a representation of the quality of earnings and growth outlook for a stock.

So next I'm going to go through a couple of Excel examples to show what can actually go wrong when the PEG ratio is used incorrectly according to theoretical finance.

And while we do that, it will also serve as a tutorial for how you can conduct PEG analysis yourself.

Now I'm going to show you how to do some PEG analysis yourselves and go through a couple of examples to illustrate what can go wrong when you use the PEG ratio incorrectly when you're investing.

So we're going to look at what can happen when you buy a stock with a PEG ratio of less than one or sell a stock with a PEG ratio of greater than one in accordance with financial theory.

And show that it's actually much better to think of a PEG ratio as a signal of quality for a company's earnings and earnings growth.

And the process we're going to use is fairly simple.

It's basically just going to look at historical price data and historical PEG ratio data for a given stock and see how they relate to each other over time.

So the first thing we need to do is obtain the data.

Now in this video, I'm actually going to skip over how we obtain price data since we've already covered that in previous videos using Yahoo Finance.

But what I will do is briefly show you how to obtain PEG ratio data and import it into Excel and compare it with your price data.

So to do that, we just need to go to Ycharts.com and then in this example, I'm going to look at the stock Ralph Lauren.

So I'm going to type in RL and select Ralph Lauren from the drop down menu.

And then to find PEG ratio data, just select data and from the performance metric drop down menu, just find PEG ratio and click on that.

And that gives you the historical PEG ratio data for the stock that you're looking at.

And it begins with the date that is last available for that stock.

Now, unfortunately, in Ycharts, it's actually not possible to export data properly in an Excel file unless you pay for a subscription.

But you can actually get the data in a much more crude fashion, which is what we're going to do in this video.

And that simply just involves copying and pasting the data from the website into Excel.

And obviously, this takes a little bit more time than a normal data file would.

So I'm not actually going to go through the whole example because it's going to involve about two years of data.

Instead, I'm just going to show you a couple of pages of how you get this data into Excel.

And then we're going to use a pre-made Ralph Lauren spreadsheet ready for the analysis later in the video.

So it is literally as simple as copying and pasting.

So if you just select all the data that you want, including the date and the PEG ratio from the webpage, and then within that selection, click Copy, right-click and copy.

And then I'm going to paste this into this pre-made Ralph Lauren spreadsheet and just paste it into a cell in Excel.

That will give you your date column and your PEG ratio column, and they'll all line up correctly.

All you need to do is delete the break in the data set halfway down.

And then you've got a consistent data set.

So then all you need to do is go to the next page of data, and you can keep going back as far as you want.

Do this for however many pages of data you want.

Keep going, copy and paste that in below your previous data, and delete the break in the data set.

And then once you've done that and gone back as far as you want, you'll end up with something like what I've got here on the left-hand side in columns A and B, with the date and the PEG ratios.

And then all you need to do is go to Yahoo Finance and obtain the daily closing price data for all the dates within your date range.

And make sure they correspond to the correct ones.

So the easiest way to go about conducting our analysis, our PEG ratio analysis, and looking at how it relates to the price over time, is by making a chart.

So that's what we're going to do first.

We're just going to select all the data, and then insert a line chart of this data.

And that gives us the line chart of all the relevant data that we require for our analysis.

The first problem we've got here is a scaling problem.

So at the moment, the PEG ratio data is stuck around a value of 1, and it's using the same axis as the price data, which is around 150.

So we're going to create a secondary axis for the PEG ratio data by selecting the PEG ratio line and right-clicking on it and formatting the data series, and then adding a secondary axis here.

That gives us a secondary axis, a PEG ratio axis on the right-hand side.

And the next scaling problem we're going to resolve is the price data just hanging around at the top of the chart, when actually, in order to sort of visually interpret it more easily, we want it to use much more of the chart.

So we're going to change the left-hand axis, the price axis, to have a minimum value of something greater than zero.

So to do that, we left-click the axis, then right-click, format axis, and change the minimum fixed value to, in this case, 100.

So now we can visualize the PEG ratio and stock prices relationship over time.

So let's have a look at what would happen if we bought and sold the stock in accordance with financial theory, i.e., when the stock is over and undervalued according to the PEG ratio.

So, remember, with the PEG ratio, a stock is overvalued when it's above 1 and undervalued when it's below 1.

So we're going to insert a line at a PEG ratio of 1 so we know that when the PEG ratio goes below 1 and is above 1.

And I'm just going to format that object by right-clicking on the line and changing the line color to black and making it a bit wider.

So now we can see the date range when the PEG ratio is less than 1, i.e. undervalued, and the range when it's over 1 and overvalued.

So now what we're going to do is go through the chart chronologically and add in buy and sell signals in accordance with financial theory by adding lines to the chart, vertical lines, green and red lines for green for buy and red for sell.

And we'll do this at the major changes in the PEG ratio.

So, like this change here from below 1 to above 1 and here and so on.

And those changes that actually come about from changes in EPS and EPS growth estimates.

So, let's start now by, we're going to start at the very beginning.

So, September 2011, we're going to say that's a buy signal in accordance with financial theory because the PEG ratio is less than 1, representing undervaluation.

So, we should buy the stock in anticipation that the stock price will rise.

I'm just going to make this a bit wider and green, this line.

Because that's what financial theory dictates.

Now, the next major change is in, at the end of December 2011, where the PEG ratio rises from less than 1 to greater than 1.

So, it's going from undervalued to overvalued.

And so, that can be regarded as a sell signal.

And then again, at the end of March 2012, it goes from above 1 to below 1, overvaluation to undervaluation.

Remember, these significant changes in the PEG ratio are down to revisions to a company's EPS and EPS growth estimates.

So, that is a buy signal because it's dipping below a PEG ratio of 1.

And the final line we're going to insert is at the end of June 2012, where the PEG ratio rises from less than 1 to above 1, representing overvaluation, and hence is a sell signal.

So, now let's consider what happens to the stock price after our buy and sell signals through this chart.

So, September 2011, we've got a buy signal, but actually the stock price falls to the next sell signal.

And again, similarly, we then have a sell signal, but then the stock price is actually rising to the next buy signal.

And this happens consistently through this chart.

So, essentially, the stock price is actually doing the opposite to what financial theory should dictate.

So, why is this happening?

What is actually happening here?

Starting from the beginning, September 2011, the market is actually selling the stock in anticipation of EPS and EPS growth decline.

So, effectively, it's pricing in the company's revision to EPS and EPS growth estimates, which then happens here when the PEG ratio rises from less than 1 to above 1.

So, the revision is downwards, hence the stock price is pricing that in before that happens.

And then, again, the market begins to buy the stock in anticipation of higher EPS and EPS growth.

So, they start buying the stock somewhere around January 2012, in anticipation that EPS and EPS growth rates will be revised upwards.

And then, they're actually proved right come the end of March 2012, where EPS and EPS growth estimates are revised upwards.

And, hence, the PEG ratio has a fall in value, and that happens again in the next segment of the chart.

And then, post-June 2012, we can see a good example of the market continually buying the stock and paying for good quality earnings and growth, which effectively rewards the company for anticipated EPS and EPS growth revisions upwards.

So, now we're going to briefly look at another example, where it's even more obvious that the market's willing to pay for good quality earnings.

And that example is a company called 3M.

So, we're just going to briefly go through the same analysis, although this one's much quicker.

We don't need to add in all the lines that we did in the previous chart.

So, first thing to do, create the chart by selecting all the data, clicking insert, insert simple line chart, and we're going to resolve our scaling problems again.

So, we're going to add a secondary axis for the PEG ratio data by selecting the PEG ratio line, right clicking format data series and adding second axis.

And then, again, our next scaling problem will get the price line to use a lot more of the chart by right clicking on the price axis and changing the minimum fixed value to 70.

So, in this example, over the whole period that we're looking at, about a year-long period, the company is actually being rewarded through a rising stock price for anticipated EPS and EPS growth rate revisions upwards.

And, needless to say, following financial theory, would actually lose a lot of money on this stock as well.

So, you can now use this analysis yourself when generating trade ideas as a supplementary tool to looking at PE ratios.

With PE ratios, if we have long ideas, we're looking for PE's on a premium to the sector, and for shorts, we're looking for PE's on a discount to the sector.

And this is because we know that high PE ratios mean that the market's willing to pay for high quality earnings, and with low PE ratios, the market's actually punishing the stock for low quality earnings.

And then, we can look for reasons as to why this is the case.

So, if there's no reason to go against the market, then it's very clear that you don't know anything that the market doesn't know, and you're actually fighting the trend.

Similarly, you can look for long ideas with PE ratios above 1 and short ideas with PE ratios of less than 1, and you'll see that, as with the PE ratio, the market will continually reward companies with higher than sector average EPS growth, and punish those with lower than sector average EPS growth.

So, that's all you need to know about PE ratio analysis.

I hope that you can incorporate this into your investment framework successfully, and good luck with your trading.

Good luck with your trading.
