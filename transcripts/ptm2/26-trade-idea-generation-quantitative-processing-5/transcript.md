---
course: ptm2
lesson_id: "26"
title: "Trade Idea Generation - Quantitative Processing 5"
module: quantitative-idea-generation
module_title: "Quantitative idea generation"
duration: 02:29:05
duration_seconds: 8944.917
source: "26. Trade Idea Generation ΓÇô Quantitative Processing 5.mp4"
model: "ggml-large-v3-turbo.bin"
related_documents:
  - "Documents/Video 26/EG_Profiles_Shorts.xlsx"
---

# 26 — Trade Idea Generation - Quantitative Processing 5

Okay, guys, welcome back to the desk again. So in the last video, we looked at the mechanics of long idea processing. Then Chris showed you how to process sector and stock data and each of the steps that you would go through to identify positive and negative outliers. And of course, potential. So the key word there, guys, potential, long and short outliers. So the key word there, guys, potential, long and short outliers.

Now, long idea processing. What did we actually do there? Well, we identified all of the earnings growth profiles for forward-looking earnings growth estimates, expectations, as said by research analysts in the market. So this is our earnings growth one number and our earnings growth two number. And we overlaid this with our own requirements. requirements to have the market on our side. And we rank the earnings growth profile estimates in preference for growth. So we then, of course, take that analysis and we apply it to a sector whenever we are processing the data in a sector. And Chris, of course, showed you with the spreadsheet class, how to download the data and process it and process it with best practices steps. In future, what you're going to be doing is you're going to become very, very familiar with all of these earnings growth profiles. And whenever you're processing, they're going to always be in the back of your mind. So you will naturally go through the processes very, very quickly. And you'll just get better and better at this.

At using the earnings growth profiles, ranking them with preference and ranking stocks with preference to their growth when you're processing data. So eventually, you'll end up doing this without thinking about it too much. And it becomes an autopilot situation. So you can probably see where this is going now, guys. Yes, conscious competence.

You're going to become competent at doing this. Practice the processes over and over and over until you get good at it. And of course, get used to it and you start doing it naturally without thinking about it too much. You will start identifying opportunities without thinking about the earnings growth profiles too much. You'll end up doing it naturally. Now, we're going to move on to mechanics now of short trade idea processing. We're going to take the same approach by systematically going through earnings growth profiles. But now we're looking at them through a short lens, which requires actually a very different approach. In the video after that, what we're going to be looking at is turnaround stories and value traps. And we're going to learn what to stay away from and what could be opportunistic in that space. Then, in the video after that, we're going to be looking at the most common mistakes in data mining and processing. So, in the quant phase, the mistakes that are commonly made by retail traders in the quant phase, when data mining and processing during the bottom-up process. This is actually going to help you a lot in cementing the processes that Chris taught you in the previous video. So, let's shoot over to the next video and I'll see you back at the desk a bit later on.

Okay, so we are back at the screen. Video number 26. We're going to continue now with our trade idea generation processes. And we're going to be looking at the mechanics of short trade ideas. We are again going to be looking at percentage earnings growth as a filtering metric within the quantitative phase of the overall bottom-up process. And here, again, we have our quantitative and qualitative dashboard as a reference point as to the entire bottom-up process. So, on the left-hand side, we're going to be focusing again, like in the last video on earnings growth, except in the last video, we looked at longs. In this video, we're going to be looking at shorts. In terms of the assumptions that we're going to make in the backdrop of establishing a portfolio bias, well, in the previous video, we looked at the quantitative processes that pro-traders focus on at the stock level when we're generating potential long ideas.

And we assumed a bullish macroeconomic view and a net long portfolio bias. So, we assumed that you recognized that the world is in a cyclical upswing, that you're forecasting real GDP expansion with Fed target inflation intact and that your portfolio bias is net long and you want to be aggressively long growth stocks in your portfolio. In this video, we're going to assume the same. However, we're looking for shorts against longs that are in that portfolio. And this is a big lesson in itself.

Because at any one moment in time in the future, even if you want to be aggressively long growth names, because you have a bullish predisposition, you must always, always, always, always still be seeking out shorts and seeking out shorts that will go down in value, even if the overall stock market goes up.

And the opposite also holds true. Even if you want to be aggressively short growth names, because you have a bearish predisposition, you must always be seeking out longs, and seeking out longs that will go up in value, even if the overall stock market ends up going down.

As traders and portfolio managers, we can't just be naked long or short everything and be 100% 100% in one direction. This is a surefire way to blowing up your trading account.

Now, just as a reminder, we always want to be going where the juice is. So remember, we have our entire US stock market that encompasses over 2200 stocks. Within the stock market, we have our industry sectors that have both cyclical and defensive characteristics. And within all of those sectors, we have different types of stocks that exhibit different types of characteristics. We have growth names, we have X growth names, and we have value names. On the short side, we're looking to be short, X growth names, and potentially value names or value traps. On the long side, in the previous video, of course, of course, of course, what do we like? Well, we like what all money in the stock market likes, which is growth. So on the long side, we seek to be long growth names. And on the short side, we seek to be short, X growth names, and potentially what we call value traps. So whether it's X growth or value trap, and regardless of what sector the stock is in, we always want to be optimizing in any GDP growth environment. So regardless of whether GDP is growing or contracting, we want to be short stocks that go down in value. And we want to be short stocks that underperform the sector and the market in any GDP environment. In this example, as mentioned earlier, we are assuming a net long bias in the portfolio, emanating from an analysis of the macro environment, where we believe that GDP will expand and the stock market will go up. So in the backdrop, we have a net long portfolio bias, and we are long growth names in the portfolio. And we are seeking to add shorts to that portfolio. Now, similar to the previous video, where we looked at those 10 earnings growth profiles through the lens of long ideas, so long idea processing. In this video, we're going to be looking at various earnings growth profiles, but looking at them through the lens of short idea processing. And you can go into the download section, and download the spreadsheet called earnings growth profiles for shorts. And you can see all of the earnings growth profiles in that spreadsheet that we're going to look at here. But first, we need to talk about some of the mechanics of potential short trade ideas, some technical situations, and some good habits.

So if you recall, from the previous video, with our market cap filters, with short ideas, you need to be concentrating on the $20 billion plus market cap space. From a short perspective, from a revenue perspective, perspective, from an earnings perspective, a large cap or mega cap stock has more potential to halve once it goes X growth in a lower risk way than a mid cap, or even a small cap stock or a micro cap stock.

From a long perspective, a mid cap, say $5 billion market cap stock has more potential to double and double quickly than a mega cap $40 billion plus market cap stock. So for long ideas, if you recall, we need to concentrate on the $3 billion to $10 billion market cap space. For shorts, we need to concentrate on large cap stocks that have $20 billion plus market cap and mega cap stocks. For mid caps, earnings growth is generally greater than in large and mega caps. For shorts, we are looking to get in when growth is slowing. So when a stock goes X growth. So you have to use market cap as a filter, as well as price earnings ratio, earnings growth, and peg ratio. So again, we are continuing here to build out a portfolio where we're using essentially volatility as a filter. So we have a portfolio that presents us both acceptable risk and good opportunity to make money. And that, of course, as you've seen before, was covered in the IPLT video series. If you haven't seen that, then I suggest you do register and subscribe.

Because again, this is how everything fits together. So from a portfolio volatility perspective, the large and mega cap space is ideal for us, because initially, there is low volatility for the 20 to 60 day time horizon. But because their business models. And they are vulnerable. When something happens to these companies in the negative, so when they go X growth, that's when stocks fall and fall sharply and volatility increases significantly. So we as traders and portfolio managers want to be capturing those moves.

Additionally, when we are using market capitalization as a quantitative filter for our short idea processing, when we are opening a trading account for the first time, we want to get off to the best possible start.

If you fill your portfolio with low market cap shorts. So under $3 billion. And you have lots of longs that are over, say, $40 billion. So essentially, you are short small caps, and long mega caps, you are asking for trouble.

So in a GDP growth environment. So in a GDP growth environment, for example, when you have a portfolio bias of net long, earnings growth is larger and more sensitive to the business cycle in, for example, you are short mid caps versus large and mega caps on average. So if you are building portfolios, where for example, you are short a mixture of mid caps and small caps, and long a whole bunch of mega caps, and you're just starting out with a new trading account, you are asking for trouble because you are short on average, higher earnings up revenue growth versus long, lower earnings up revenue growth on average. So you are exposing yourself to being short high earnings growth, and high revenue growth, and long low earnings growth, and low revenue growth. You are also exposing yourself to short high volatility, and long low volatility. So this is exactly the opposite of what we're trying to achieve here, as traders, when we're building long short portfolios, you are asking for trouble. And as time goes by, you will blow up. Additionally, you're exposing yourself to potential takeover risk in your portfolio.

Because if you're short, a whole bunch of low market cap stocks, and long a bunch of high mega cap, or large cap market caps, you're exposing yourself to your low market cap stocks being taken over.

They are much more likely to be taken over mid caps than a large or mega cap.

Why? Because it's much easier for large companies to get the financing to acquire or take over, for example, a mid cap company that currently has a $3 billion market cap, and they go and buy it for $4 billion or $5 billion, as in they pay a premium for that stock, for that company. It's much easier to do that than to go out and raise the financing for a $7,500 or $150 billion market cap stock.

Additionally, large companies who are looking to acquire other companies, they are going to be more attracted, like us, to growth. They are not going to be attracted to X growth, they're more likely to be attracted to growth. So again, larger companies will be more attracted to smaller stocks, rather than large or mega cap stocks or companies simply because of their growth.

So it's easier to get the financing on a much lower market cap because of the chip size, the size of the deal versus the size of the deal of a large or mega cap. But also, using that financing, companies would rather acquire growth, they are more attracted to growth, like us. But also, just from a risk perspective, from a trader's perspective, when we're looking to short stocks, let's have a look at a takeover risk example. So let's say you have a trading account of $15,000 deposited on margin, and you have the ability to leverage this four times. So you can have a $60,000 gross exposure portfolio. And let's say in the portfolio, we choose to have eight positions of $7,500 notional exposure. And within those eight, we have five longs and three shorts, but we choose to be net long, five large and mega caps, and short three mid caps.

What actually happens if, for example, we short $7,500 of a stock that has a market cap of, say, $3 billion. So it's defined as a mid cap, market cap $3 billion. And the company is taken over for, say, $4.5 billion value. And the announcement happens when the stock market is closed. That's a 50% premium to the market cap of yesterday. The stock will simply go up 50% without you being able to get out. So you're going to be down $3,750 on the trade. So on a total gross exposure number of $60,000, you are down $3,750, which is a 6.25% loss on the gross exposure number. But on the margin number of $15,000, that is a 25% loss on your margin. This is an irrecoverable position for an account size that's this small.

It's going to take the risk that's this small. It's going to take you at least 6 months, possibly even 12 months to make this money back in the portfolio. This type of risk has to be eliminated from your portfolio immediately. So from the outset, you must do, you have to place a market cap filter on your short ideas of $20 billion minimum. So only go short, large and mega cap stocks to begin with. When you're making money six to 12 months down the line, only then are you allowed to get clever, but not in the beginning.

You've not earned the right yet to be clever because you haven't made money.

Now coincidentally, this is why good shorts are much harder to find than good longs in a typical positive GDP environment. Why? Because we have to place a market cap filter of $20 billion from the outset.

And just from a market cap perspective, there's going to be less of these stocks available in the market.

So the opportunity set is just smaller. Additionally, within the opportunity set of the $20 billion plus market cap market cap stocks available at any one time, we have to find fundamental setups that exhibit characteristics of good short ideas. So not only is the opportunity set smaller than our potential long stock ideas, but within the opportunity set, the amount of stocks that any one time that exhibit fundamental characteristics that enable us to be short these stocks is much smaller. But remember, we are looking through the lens here of a positive GDP environment. It's much harder to find good shorts in that environment in a slowdown in GDP. So when GDP is slowing down and still positive, but it's going lower. Or in a GDP contracting environment, it's obviously much easier to find shorts. But remember, one thing is for certain. In any GDP growth environment, we can't simply be long 100% in our portfolio or short 100% in our portfolio. We have to have either a net long or net short bias or a neutral bias. In this example, when we're looking at a typical positive GDP environment, we still have to have shorts in our portfolio. And we have to do the work.

We have to generate as best we can, good short ideas, even in the typical positive GDP environment, and we must have short positions in our portfolio. Now, similar to when we were looking at long ideas, we do have an ideal ideal price earnings ratio set up for short ideas. So our backdrop, what we want to be having is something like this for our PE profile for the stock relative to the sector. So when you're filtering for PE, you are looking for for stocks that have a PE that's on a discount to the sector in both period one and in period two. But in period two, the PE two, because we're using current stock price divided by EPS, we want the PE two to be higher for the stock relative to its PE one. Why? Because it means that EPS is going lower in PE two versus PE one. So we have lower EPS in PE two versus PE one, and therefore negative earnings growth.

Additionally, in this earnings growth profile relative to the sector, you'll see with the sector that the PE for PE two is lower than PE one, meaning that the sector is actually exhibiting some sort of growth.

So that means that the average mean earnings per share of the sector is actually growing slightly from period one to period two. Now it could be even better, for example, if the EPS, the mean EPS of the sector is either the same or lower for the second period versus the first period. But what we've done here is exhibited a case where it's just slightly better. So the PE for period number two is just slightly lower than PE one. And that's kind of the minimum ideal PE setup or PE situation for the sector.

And then with the stock relative to that, we want lower in both periods. And on top of that, for the stock itself, we want to see EPS lower in period two versus period one. Now, just as a side note, this is a situation where EPS is positive in both periods for both the stock and for the sector. So yes, we will be looking at earnings growth profiles of loss making companies. But here we are looking at a company that is in profit, but their profit, their EPS is going lower. And this is the ideal setup for us in terms of EPS and price earnings ratio for the stock versus the sector. So in this situation, the stock is potentially going X growth in a sector that is growing slightly. So this is the backdrop, the minimum backdrop that we are looking for, the ideal price earnings ratio set up when we're processing for short trade ideas. When we move on to earnings growth, it becomes a slightly different story into how we analyze earnings growth through the filter of a short lens when compared to when we do this exercise, looking at earnings growth profiles through a long lens.

So if you recall, when we looked at sequentially positive earnings growth, when we looked at long ideas as the ideal situation, what did we have? We had an earnings growth one percentage that was higher than the sector, higher than the mean average. And then in EG2, we again had a stock earnings growth number that was higher than the sector, but in earnings growth two for the stock itself, it was higher than in earnings growth one. So we had a sequentially positive earnings growth number for the stock that is outperforming the sector, that is outperforming the sector in both periods. Now on paper, if we just reverse that situation and we say, okay, we just turn this upside down. And that's what we're probably looking for for shorts. What do we get? Well, we get in period one, an earnings growth number that is negative.

And worse than the earnings growth percentage in period number one is negative. And then in period number two, it's negative again, and it's accelerating to the downside. And again, it's underperforming the sector. So the stock's earnings growth is negative in both periods.

And it's getting more negative in period two versus period one. And in both periods, it's underperforming the sector. So on paper, what we're essentially getting here is sequentially negative below sector average earnings growth momentum.

The problem is, the problem is, is that with shorts, the earnings growth setup can look attractive on paper.

But when you actually go into the market and have a look at stock prices that exhibit this scenario, they're probably already going to be down quite a lot. And yes, on the flip side, when we're looking at long ideas that exhibit sequentially positive above sector average earnings growth momentum, when we pull up the stock prices of those companies, you're probably going to see the companies up quite a lot.

But there is sometimes a difference in that when we're looking at long ideas and we're looking at valuations and earnings growth and we're looking at price.

We saw in the previous video that for a company to maintain its same PE ratio, that the company in the positive would have to be hitting its earnings growth numbers, its EPS, and the stock can continue trading on the same PE, the same multiple in the second period.

In that situation, the market continues to reward the company with a premium to the sector for delivering continuously on its results, on its operations.

Yes, the stock in the journey with sequentially positive above sector average earnings growth momentum in that journey from period one to period two, it can be volatile.

But ultimately, if the company keeps delivering, it's highly likely that money is going to continuously reward the stock, reward the company, and the company will continuously trade on a premium to the sector.

The differences with shorts when we're looking at sequentially negative below sector average earnings growth momentum, it's likely that when we pull up this type of earnings growth profile and then go and look at the stock price, the stock price, it's likely that the stock price is going to be down potentially quite a lot already.

And management is going to be doing things in an attempt to stop the bleed, to stop the earnings decline.

So there will be dynamic actions occurring potentially in the market when we have a static on paper earnings growth profile in a stock that can already be down quite a lot.

And if a stock is already down quite a lot and it's exhibiting this type of earnings growth profile, then stocks, when they get to certain levels, can actually represent to the market value.

And this type of value appraisal comes from other players in the market, investors who are looking at both the balance sheet and the operation and coming to the conclusion that at a certain level, a stock is value.

So we have to look at sequentially negative below sector average earnings growth momentum in the same way that we look at sequentially positive above sector average earnings growth momentum.

This earnings growth set up, this earnings growth profile on paper looks ideal, but it is static and only on paper.

And things can change and things are dynamic day to day in the market.

And we have to be very careful that we don't, for example, short stocks that are down a lot already and management are doing things to turn around the company, to turn around the fortunes of the company and turn around earnings growth.

And on top of that, stocks are not at a level where they represent value, where investors are stepping in.

So sequentially negative below sector average earnings growth momentum looks ideal on paper, but it is hard to get in at good levels when the market now knows that this is the case.

It's likely that stock prices have already moved down quite a lot.

So we have to be careful in our analysis and treat it differently to sequentially positive above sector average earnings growth momentum.

Additionally, when we are identifying X growth stocks, this does come with some caveats.

When we are identifying X growth stocks, it means that the stock is very clearly beyond its growth phase.

When you look at further metrics like revenue growth, for example, the stock may be still in its growth phase.

And the management operating plan is to choose to reinvest revenue and therefore earnings into growing the top line.

So in this situation, the stock is a revenue growth story.

So don't think because you see negative earnings growth in an earnings growth profile that a stock is automatically a short.

It isn't.

It isn't.

You always have to do further work.

More work is required.

If this happens to you in your identification phase in the quant for short ideas.

If this happens to you, it's okay.

What you've done is, is you've just identified a growth stock by going through the process and you've learned more about the stock and more about the sector.

This is why we have a filtering process.

We are in the process phase of identifying potential shorts.

And sometimes when you're looking at shorts and you're looking at earnings growth profiles and looking at them through a short lens, you're going to bump into growth stocks that exhibit negative earnings growth.

But they are still in their growth phase because it's all part of their management operating plan.

So don't think automatically that because you see negative earnings growth, that a stock is automatically a short.

It just isn't.

You need to do further work.

On top of this, you need to always be aware about something that we call in the processing phase, the law of small numbers.

We're going to be covering this later when we discuss processing mistakes in the quant phase a bit later in the PTM video series.

Now, similar to when we looked at long idea processing in the quant phase and we looked at earnings growth profiles there, we're going to be looking at a number of earnings growth profiles for short idea processing.

And the first five we're going to look at are all in a situation where they have positive EPS in both periods.

Now, we've already seen our first one, the ideal scenario on paper, which is the sequentially negative below sector average earnings growth momentum.

We're going to look at the others as well, case two, three, four and five, and then there'll be more cases later.

So case number two, we have negative earnings growth and earnings growth that's less negative in the second period.

And that's both below sector average.

We have flat earnings growth in the first period, then going negative and both below sector average for the third case.

For case number four, we have positive earnings growth that's then going flat to negative and below sector average.

And then case number five, we have negative earnings growth in period one that then goes to a flat or positive position.

And again, both below sector average.

So let's have a look at these visually.

We've seen our first one, the sequentially negative below sector average earnings growth momentum.

On paper, the ideal setup.

In reality, it may not be.

The next one is probably the next best thing that is actionable.

Negative earnings growth in period one and negative earnings growth in period two and both below the sector average.

And in this situation, we have a sector average that has positive earnings growth.

And if you think about this one compared to our sequentially negative earnings growth, if you think about this one in comparison, if the sector is the same, but we have a stock like this where we have negative earnings growth and the earnings growth situation is still negative in period two.

But the rate of the earnings growth decline is slowing.

This could potentially provide a better entry point or better short than case number one.

Why would this be the case?

Well, it could be that the market is or analysts in the market are hoping for some sort of slowdown in the rate of earnings growth decline.

And that may not materialize.

It may do.

It may not.

But we have to do more work.

The point is, is that this type of earnings growth profile is not as bearish, if you like, on paper as case number one with the sequentially negative earnings growth momentum.

So with a bit of hope priced into the stock that the earnings growth decline could be decreasing.

With a little bit of hope priced into the stock, this could potentially provide us with a better entry point, a more timely short, because the situation could get even worse than it is now.

But of course, as with anything else where we're in the quant phase, more work has to be done.

Moving on to case number three, we have a situation here where the earnings growth in period one is actually slightly positive, but below sector average.

And then in period two, the earnings growth goes very negative and is below sector average.

And in this case, we need to be quite careful.

We need to be careful here because we need to analyze what is really going on at the company.

There's obviously something that analysts have flagged for period two that is going to be very bearish for earnings growth.

Therefore, we need to work out whether this is actually operational and it's a material change in business conditions or it's some sort of technical situation through, for example, accounting.

So there could be, for example, a big expected one off charge that's going to occur in the following year that's going to hit earnings.

And this is a very well flagged and expected by the market.

So we have to understand that in those situations, the market will look through it or potentially look through it because it's not a material change in business conditions to the negative.

But when we pull up this type of earnings growth profile, we obviously on paper know for sure that earnings growth is getting hit considerably in the following year.

Therefore, something bearish is happening to earnings with the PE backdrop that we've got.

If that's intact as well, it means the market is punishing the stock.

It's trading on a discount to the sector.

And we have to do further investigation to work out whether this is operational or technical.

So in this case, we call this flat, then going negative below sector average, even if it's a tiny positive of say 1% earnings growth, it's essentially flat.

Looking at our fourth case, we have in earnings growth period one percentage, we have positive earnings growth, which is below sector average.

And then we have a situation in period two where earnings growth percentage is going to flat or negative and below sector average again.

Case four, similar to case three is showing us that the market is expecting earnings growth to be positive in period one or flat to positive in period one, like in case number three.

But it's going flat to negative in period two.

So the market is expecting an earnings growth decline for the second period relative to period one.

So again, similar to case number three, in case number four, we must do further work to figure out what this expectation in period two is all about.

Why is there an earnings growth decline expected by the market?

What is the reason behind it?

Is it genuinely operational where it's a material slowdown in business conditions?

Or is it technical?

We have to go and figure that out and make sure we understand what's behind the earnings growth decline that's expected by the market.

Now, what you will notice as we've gone through case number one, two, three and four is that you're looking at earnings growth profiles that are potentially at various stages of a company going X growth.

Case number one.

Case number one, where we had sequentially negative earnings growth momentum that is below sector average in both periods.

That could be a situation where the stock has gone X growth and it is late stage X growth.

And when you've seen case number two, three and four, these cases are potentially cases that are earlier stages of a company going X growth.

So it can be the situation that case number four, for example, is at a much earlier stage of going X growth versus, for example, case number one or even case number two.

So the stock prices may not have moved yet to reflect the full discount that the stock could potentially trade on in the future.

So when we're looking at all of these cases, we have to ask ourselves the obvious questions.

Has the company actually gone X growth?

That is the most obvious question to ask.

And then to answer that question, we have to look at the operation and find out if there is a genuine material negative change in business conditions.

And then to put it into context from a short idea processing perspective, we have to ask ourselves the next question, if it is X growth, how far along are we in terms of the stock being X growth?

And what is reflected in the share price, how much has the stock gone down already to reflect how far the stock or company is down the line in terms of going X growth?

And are we early to the trade?

Are we early to the party or are we late to the trade?

Are we late to the party?

Which brings us nicely onto our fifth case, which is a situation where earnings growth in this profile is negative in period one and then positive in period two, but below sector average in both periods.

And this situation is like what we looked at when we were looking at long idea processing where there's a potential turnaround story.

But there is a flip side to that coin because a potential turnaround story can also be a potential value trap.

So this situation here could happen in a company going X growth in the early stage, but it could also be a company that has gone X growth and has been X growth for a while.

And now the actions of management are potentially turning around the company's fortune, turning around earnings.

If you see an earnings growth profile like this, where it could be early stage X growth, then the EG2 number could be a totally fictional hope number.

And the EG1 number is reality going forward.

So EG2 could be downgraded.

So earnings in the second period could be a hope number for analysts.

So that type of turnaround could just be very low probability or fictional.

In the other case where a company has been X growth already for a long time and is far down the road of being X growth.

The stock could be down a lot.

It could be down 50, 60, 70, 80% already underperforming massively for the last one, two, three years.

And then all of a sudden we have some expectation that there's going to be earnings growth in the following year after multiple quarters and a year or two of earnings growth decline.

And in this situation, this could be a scenario where we're looking at a value play where other players in the market, investors, are looking at a stock as a value play.

That is different to when we're looking at an early stage X growth stock.

However, the dynamic in this situation in the way we view it.

So whether it's going X growth in the early stage or it's been X growth for a while, we view this in a similar way in that we look at the earnings growth to number.

So next year's number.

So next year's number.

And we ask ourselves the question, is this real?

Is it genuine?

Is it a real turnaround or is it a trap?

Now, as mentioned in the previous video, when we looked at turnaround stories, the earnings growth profile of a turnaround story can be both opportunistic and dangerous.

So they are opportunistic in that we are looking at the market's expectation here of a turnaround.

And from a long perspective, it can be opportunistic in that the turnaround actually happens.

They execute on it.

Looking at it through a short lens, it is opportunistic in that the turnaround could fail.

But it is also dangerous.

So when we look at it from a long perspective, we are taking a position potentially in a stock where the analyst in the market, the market is expecting a turnaround in earnings growth.

So we are going with the market, we are agreeing with the market, but if the turnaround doesn't happen, then of course, the stock is probably going to go down a lot and we're going to lose money.

Looking at it through a short lens.

Looking at it through a short lens, it is dangerous because we are actually arguing with the market here.

So we're saying that the market is wrong to have the earnings growth number for period number two and that we know better.

And of course, because we're going short, where there's infinite amount of downside.

So especially in the case where a stock has been X growth for a long time and then the market is expecting a turnaround in earnings growth and the stock is already down a lot.

Going short, this type of earnings growth profile in that type of dynamic can be very dangerous.

So again, with all of these profiles that we've looked at so far, we are assessing from the earnings growth profile itself, not only the direction of earnings growth, but how far down the line.

The company is in terms of going X growth.

Is it early stage X growth or is it late stage X growth or somewhere in between?

And also, obviously, we want to be finding out the reasons why earnings growth is forecasted to be negative by research analysts, by the market.

We want to look at the market and understand the context of the earnings growth decline.

So the questions are always, has the company actually gone X growth?

How far down the line is the company in terms of going X growth?

How much is the stock price growth?

How much is the stock price down and how much is reflected in the stock price move and the bearishness already surrounding earnings expectations?

What are the reasons for the earnings decline or the expected earnings decline?

And is it going to continue?

Now, just as a side note, for clarity purposes, when you're going through your processing, you'll find that when we have negative earnings growth profiles, that your peg ratios are going to be negative.

So in the context of shorts, there is no ideal peg ratio set up because peg will just be negative in our ideal or close to ideal earnings growth profiles.

Because when you're dividing a positive price earnings ratio number by a negative percentage number, you're going to get a negative.

That's just going to be the case.

And the negative peg doesn't tell us anything about valuation and what the market thinks of the stock relative to other companies.

So in these situations, when you're looking at negative earnings growth profiles from a short processing perspective, you can overlook negative peg.

As in the ones that have negative earnings growth.

So they would be our cases, case number one, two and five.

But our cases number three and four would have slightly different peg setups.

So we would have a positive peg ratio in a period number one because we have in period number one positive EPS.

We have positive PE and a positive earnings growth number.

So we have a positive divided by a positive, which gives us a positive peg in year one.

So if we have negative peg like our cases one, two and five in a positive EPS environment, it's because we have negative earnings growth.

Which from a traders and portfolio managers perspective, when we see those negative pegs, it just gives us confirmation of the numbers.

Negative peg has a weak interpretation for us.

So we take note of the negative peg.

However, we do not put too much weight on the interpretation for it.

In our cases number three and four, if we have a positive peg in a positive EPS environment, it's because we have in the period a positive earnings growth.

If we then see that peg go negative in the next period, it's because we know that earnings growth is going from positive to negative.

So from a short perspective, from a short trade ideas processing perspective, this visually is confirmation for us that we are getting negative earnings growth in the next period.

It's close to ideal or it's the next best thing.

Now we have several other cases of earnings growth profiles that we can look at for short idea processing, looking at them through a short lens.

Up next is case number six and case number seven.

So case number six, this is where EPS is positive again, but earnings growth is positive and then positive again.

Period one, then period two, but it's lower than the sector in both periods.

This is not ideal.

This is more like a hedge and we are not hedgers.

We are traders.

We want better than this.

Case number seven, anything that is equivalent to the sector or higher.

So it's just not worth looking at.

So looking at positive, then positive earnings growth period one and period two, but below sector average, what we've actually got here is for the stock itself earnings growth momentum.

So we have sequentially positive earnings growth momentum for the stock, but it's below sector average for both periods.

We could have just as easily put on the screen in period two, a slightly better positive earnings growth number.

We could have put on the screen a flat earnings growth number or slightly worse.

That would be pretty similar because it's positive and positive looking through a short lens.

In all of those scenarios, this would probably not qualify as good as the situations that we've looked at so far.

Definitely not for the sequentially positive earnings growth, even though it's below sector average.

This for an investor would potentially provide a hedge to a long idea in the same sector.

But again, we are not investors.

We are not into hedging.

We are looking for the juice.

We want stocks that are going to get clobbered.

We want stocks that are going to go down.

We want shorts that are going to go down a lot and longs that are going to go up a lot.

We want to be going where the juice is.

For case number seven, it's a pretty similar situation.

In both periods, we are exhibiting earnings growth for the stock that is at or very close to being equivalent to the sector earnings growth in both periods.

Again, this is not ideal for us when we're looking through a short lens.

We're not into sector performance.

We want to do better than this.

We want to be short stocks that are potentially going to really underperform the sector and the market in any GDP environment.

And not just underperform, but go down a lot.

Now, moving on to our next three and final three, actually, earnings growth profiles when we're short idea processing.

Now, all of these companies, at least in the first period, have negative EPS.

So they are loss making companies.

And then also in the first period, they have negative earnings growth.

But what's different about these cases is what happens in the second period.

So let's take, for example, case number eight, where we have a loss making company.

So negative EPS, at least in the first period.

And they get negative earnings growth in period one.

And the earnings growth is below sector average.

Then in the second period, they have positive earnings growth.

But that doesn't necessarily mean that it's positive EPS.

It can also be negative EPS.

But it's just less negative.

But the positive earnings growth number is above sector average.

We would again define this type of earnings growth profile as a turnaround or value trap, potentially.

So this, again, is both opportunistic and dangerous.

With case number nine, we again, in period number one, have a loss making operation.

So we have negative EPS.

We have negative earnings growth as well in period one.

And it's below sector average.

In period two, we also have negative earnings growth, but that is at or below the sector average.

So what's happening here is that in period two, the company is losing slightly more money than it did in period one.

But the earnings growth decline is lower.

So this is similar to our case number two.

Again, this is a turnaround or value trap situation, opportunistic and dangerous.

And finally, with our case number 10, our final case, we have in period one, a loss making operation, negative EPS, with negative earnings growth, that's below sector average, moving to a scenario in period two, where we have EPS growth, that's even more negative than period one.

And it's below the sector average.

So this is like our case number one, the sequentially negative below sector average earnings growth momentum.

But the company is already in a loss making situation.

So the question is here is whether we're trying to be a hero trader and trade the stock to zero, because it's highly likely in this situation, as long as this is not a revenue growth story, and it's part of the management operating plan to have negative earnings growth in order to grow the top line.

So on the condition that this is genuinely a stock that has gone X growth in a situation like this, where the company is loss making, it's highly likely that it's way down the line of going X growth.

So the question is, is how far the stock has already moved already, and if it's down a lot already, say 50%, 60%, 70%, 80%, 90%, if it's down a lot already, are we trying to be the hero trader here and trade this stock to zero?

Are we late to the party?

Are we late to the party?

Are we late to the party?

Are we late to the party?

Or are we early to the party?

In this situation, it's highly likely that we're late to the party.

So let's have a look at these visually to understand them a little bit better.

Here we have case number eight, where we have negative earnings growth from a loss making operation in period one, that's below sector average, and then we have positive earnings growth that's above sector average in the second period.

And in the second period, remember, this can also be negative EPS as well as positive EPS.

So we could have a situation here where a company, for example, is going from negative 60 cents to negative 1 cent in their earnings in their EPS.

So essentially, they've recovered 100% of their losses.

So they have 100% earnings growth in the second period relative to earnings growth in the first period.

Or they could be going from negative 60 cents to positive 1 cent.

So again, around 100% earnings growth.

It's essentially the same as losing 1 cent.

So again, as long as this is defined as a genuine X growth scenario, we can look at this as a potential turnaround or value trap.

So again, we are always assessing the context as to whether it's a genuinely X growth story, how far down the line we are in terms of the company being X growth, the reasons for it, how much the stock has moved, and in this particular situation, whether a turnaround is actually genuine or not.

Next up is our case number 9, where we have, again, a loss-making operation in period 1, where we have negative EPS.

And we have negative earnings growth that's below sector average in period 1.

And in period 2, we have negative earnings growth in period 2, that's either at or below the sector average.

And if you recall, this earnings growth profile is very similar to our case number 2, except this situation is the company is actually loss-making instead of profit-making.

So we are looking at it through the lens here, the same earnings growth profile.

We are looking at it through the lens of a loss-making operation rather than a profit-making operation, because in the first period, we've assumed that the company has negative EPS.

So again, this is a turnaround or value trap story, and we have to be very careful.

We have to put everything into context as to whether the company is really an X growth, a genuine X growth situation.

If it is, how far down the line they are, how much has the stock price moved, why is the company X growth, and also whether the turnaround or value trap exists.

Next up is our final case, case number 10, where we have negative EPS in period 1 with negative earnings growth below the sector average.

And then in period 2, we have more negative EPS and more negative earnings growth.

That's again below the sector average.

So remember, this is like our case number 1, where we have sequentially negative below sector average earnings growth momentum.

So on paper, it can look good, but in reality, it can be bad.

Because again, it's all dependent on whether it's genuinely an X growth story, how far down the line they are in terms of going X growth, how much the stock price has moved, the reasons, whether we're late to the party or not.

And of course, if there's better earnings growth profiles out there and better, more well-timed shorts.

So remember, in this situation, yes, we have the sequentially negative earnings growth momentum that's below sector average, similar to case number 1.

Case number 1.

But here, we are a loss making operation.

Case number 1 was a profit making operation.

So it's highly likely that if all of these X growth factors are in place, that this scenario, we are way further down the line of this company being X growth than even case number 1.

So this covers our 10 earnings growth profile cases when we are processing in the quant phase for short ideas and looking at these earnings growth profiles through the lens of short ideas.

And as mentioned, we have to take a different approach versus when we're looking at long ideas and going through the processes there in the quantitative phase and looking at earnings growth profiles through the lens of long ideas.

So for earnings growth profiles, when we're short idea processing, we've got to think of it in terms of EPS and earnings growth in four ways.

We have positive EPS with negative earnings growth.

We have positive EPS with positive earnings growth.

We have characteristics where we have negative EPS, so loss making operations with negative earnings growth.

And we have loss making operations, so negative EPS, but have also positive earnings growth.

Now, intuitively, you would think that just finding companies that lose money would make great shorts.

So loss making companies automatically becoming great stocks to short, but that is not necessarily the case here.

You have to be very careful because stocks may have already traveled and you could be shorting something that's already down a lot.

So shorting it in a hole.

So it could already be down 50, 60, 70, 80, 90%.

And you could be very late to the party and get caught out being short.

Remember, markets are forward-looking animals.

We are forward-looking and we're not ever backwards-looking in our analysis as traders.

A stock, for example, that was a $50 billion company three years ago, that is down, say, 80%, is now a $10 billion market cap company.

On that journey from $50 billion to $10 billion, they may have had positive EPS, but had gone X growth and fallen into negative EPS, so fallen into losses.

And this is partly why we have a market cap filter on shorts.

We want to be looking to go short stocks that are going on that journey, and we don't have to capture all of the journey.

In fact, for both longs and shorts, we always want to avoid trying to pick bottoms and tops.

So in the classic long setup where we have sequentially positive earnings growth momentum, we are playing the earnings growth and we are playing that momentum.

But even if we are wrong, our gap risk to the downside on a long position is 100%.

We can only lose 100% of our money on a long stock position.

In the classic short setup that we looked at where we have sequentially negative earnings growth momentum, we are potentially playing the earnings growth decline.

But in that scenario, our gap risk is actually infinity.

On a short stock position, we can lose an unlimited amount of money.

And for both long and short positions, with long positions, the gap risk is 100% whether we buy something that's up significantly over the last one, two, three years, or whether we buy something that is down significantly over the last one, two, three years.

With shorts, the downside is infinity whether we short something that's up a huge amount over the last one, two, three years, or whether we short something that's down a lot over the last one, two, three years.

It simply doesn't matter.

So this is why we have to treat shorts and earnings growth profiles differently than how we treat long earnings growth profiles.

Because in shorts, we can get caught out and potentially lose a lot of money very quickly.

So this is partly why we have a market cap filter on shorts.

We are putting a market cap filter on to lower the probability that we're going to get caught out and lose a lot of money on our shorts.

For example, eliminating the takeover risk element in the short.

And what we're looking to do is go short X growth names that are either large cap or mega cap in characteristic.

So we're looking to short X growth names that are either mega cap and they're going to in the future become large cap.

Or we're attempting to short X growth names that are large cap and at some point in the future, they're going to be mid caps.

What we're also trying to avoid with shorts is to short or attempt to short stocks at the top.

So we're not trying to pick the top here.

So we're not trying to pick the top here.

What we're trying to do is look for evidence of stocks going X growth and with attempting to capture a part of that journey.

So for example, on the journey for a $50 billion stock becoming a $10 billion stock, maybe we can capture half of that move.

So when we look at earnings growth profiles that are negative and also when we see turnaround stories or potential turnaround stories or value drops, when we look at them through a short idea processing, short idea lens, we have to be very careful.

So for example, when we see an earnings growth profile that has sequentially negative earnings growth momentum, whether that's a loss making company or even a profit making company, we could be too late to the trade.

Additionally, if we see a turnaround stories or potential turnaround stories, which are also potential value traps.

Again, whether it's negative EPS or positive EPS, we could be in a situation here where we are late to the party.

So we have to be very careful and take a different approach versus long idea generation.

Now, recall the ideal price earnings ratio set up where EPS is positive.

It has to be, otherwise PE would be negative due to a negative EPS.

So in our ideal PE backdrop, our ideal PE setup, we have a positive PE ratio that's lower than the sector average.

And then in period two, we have a slightly higher PE, but again, it's lower than the sector average.

What's not ideal from a PE setup perspective for the PE backdrop is for example, if we have negative EPS in both periods.

Why?

Because we may have gone already on the X growth journey and the stock may already be down a lot.

And we are now in a loss making period coming from a profit making period.

So if the company is loss making and we have negative PE in period one and negative PE in period two, we got to be very careful.

We have to look at the context here and figure out where the company has come from previously and where it is now in comparison and whether it's already got on its X growth phase, whether it's very late in the stages of the company going X growth.

Because this situation here, where we have negative PE in period one, where the company is loss making.

And then in period two, the PE is still negative, but it's higher.

Now, we could be walking into a short trap here.

We could be walking into a turnaround story.

But of course, again, it could also be a value trap where the turnaround story doesn't materialize.

We still have to do further work to work it out, but it's not ideal.

Now, one of the best ways to think of how we look at earnings growth profiles and how we look at shorts and earnings growth profiles is to think of it in terms of a roadmap.

And where on the journey do we think we're actually capturing the X growth company?

So we tend to think of things in terms of short waves.

So when we have forward looking fundamentals, so expectations are shifting from positive to negative.

So we have an X growth story.

Stocks tend to travel lower over a period of time in several waves.

So here we have characterized five phases of an X growth story.

So let's start with phase one, P1.

This usually begins with some sort of capacity or market size issue.

So the company has reached a growth capacity and the stock starts to put in several tops.

This period of time is usually associated with a lot of bullish hubris in the market that the company can always continue growing at the same pace forever.

On top of that, the company itself is usually reluctant to issue any bearish estimates and always attempts to calm the market several times by just reiterating guidance over and over.

The next phase of an X growth story is phase two, where expectations actually do shift lower.

And they are now those expectations being started to believed by the market.

This period is usually associated with a lot of profit taking from long term investors.

So long term bulls on the stock or cutting from more short term players in the market from hyperbolic bulls that bought at or near the top.

At this stage, usually what happens is the company actually does issue materially lower guidance, but they do it reluctantly.

But what happens is, is by the time the company has actually issued that materially lower guidance, the stock has already moved down before they do.

And this tends to be because analysts have already moved their expectations in the market.

And the company lowers their guidance later because they are reluctant to do it, but they end up having to admit it.

Now, this brings us on to phase three, where in the market, a new normal growth rate expectation is set by the company and equity research analysts.

And this flushes out more of the stale long investors.

And what tends to happen with these situations is that it's accompanied by the company now actively seeking a new management operating plan, an MOP, and starts to talk and verbalize about a turnaround.

And then new investors begin to enter the market, usually dollar cost averaging on the way down for the turnaround story that they believe in, that the company is now pushing in the market.

Stale bulls and investors who don't believe the turnaround story sell to those that do.

But in phase three, what usually happens is the stock takes another leg lower.

And now we move on to phase four of when companies go X growth, where the stock is now down materially from its highs.

So we're talking 50, 60, 70, 80, even 90% plus.

And at this stage, it's a totally different company to the one prior to and in phase one.

And what tends to happen at this stage is the new company management operating plan is rolled out and the market is starting to see evidence that the rate of decrease in fundamentals is slowing down.

So the market is starting to see evidence that the bleed has stopped or it's close to stopping.

And the question always is here, will they pull it off?

Will they pull off the turnaround?

But from a trader's perspective, we look at it from the perspective of who really cares?

Because we want to be shorting stocks way before phase four happens.

So we want to be shorting stocks in phase two and phase three.

In phase one, we're not looking to pick the top.

In phase four, we are not looking to short stocks in a hole.

In phase four, stocks can trade sideways and occasionally have very ugly rallies, very ugly short squeezes.

And there's a lot of volatility around, but ultimately stocks will probably go sideways.

But we don't want to be caught up in that as traders.

And then what happens, we have phase five.

And in phase five, either the company management pulls off a turnaround.

So they manage to turn the company around or they don't.

But at this stage, as traders, we don't care.

We are traders, not investors.

What we are looking to do is catch phase two and phase three and then move on to the next one.

So with these short waves, of course, every situation is different and should be judged on its own merits.

This is just a rough guide or template as to when a company goes X growth and handles it badly.

So they go all the way from phase one to phase five.

On the journey through phase one, phase two, phase three, a lot of company managements could potentially see the issue coming and simply pivot in phase one or phase two, or even in phase three.

But don't worry.

This is why we have diversification in our portfolio.

Now, bigger companies tend to find it hard to turn around X growth situations quickly.

A speedboat, so a smaller company can zip around the ocean quickly.

The company, a smaller company can tweak their management operating plan to suit the times and implement across the board.

And lines of communication in smaller companies are quicker and they can get to market a lot quicker.

With larger companies, they are like oil tankers.

They move slowly around the ocean and innovation tends to be slower.

And management operating plans can't change and they can't go to market immediately.

And lines of communication in larger companies tend to be very slow and cumbersome.

So when you think of the market cap space of mid caps and large caps and even mega caps, look at it like this.

Mid caps, the three to $10 billion market cap space.

Large caps, the $10 to $40 billion market cap space.

And of course, on top of that, we have mega caps, $40 billion plus.

So think of it in this way.

If you go long a $7.5 billion market cap, mid cap company and short, say a $30 billion market cap, large cap company.

If the mid cap doubles and the large cap halves in one year, they meet in the middle at $15 billion market cap.

Now for the record, for long ideas, we don't have a similar wave template for classic sequential earnings growth long profiles.

Because in the way they journey, it can be very varied.

So how the stock travels to the upside can be extremely different from one case to another.

With short ideas, when companies go X growth, the wave template exhibits a very typical average profile of how a stock journeys throughout the waves.

So let's have a look at some real examples here.

So we can see on the screen here, Under Armour, which is an apparel brand.

And this is Under Armour going X growth and traveling from being a $25 billion stock at $50 a share to becoming a $5 billion stock at $10 a share.

So what you can see on the screen here is the various phases like in our short wave template.

So we have phase one, which is where the company puts in a top in 2015, falls and has its first move down and then trades sideways between $40 and the high $40.

You can see where the red arrow is pointing at the first red arrow.

This is where phase one begins.

And then the stock drops from mid-40s into the high 30s and treads water in the high 30s and low 40s.

So this is the stage where the company is threatening to go X growth.

But at the time, of course, management will have been reiterating guidance and defending the stock, defending the company.

But the growth trajectory of revenue and earnings that they experienced say from 2012 to 2015 and the beginning of 2016 was now in question.

So the company was potentially going X growth.

And then we have the phase two period where it's actually confirmed that the company is going X growth.

And then we have the phase three phase where a new normalised growth rate, which is slower than the old growth rates, is set as an expectation by the company and the market.

And we end up in the mid-20s and even the low 20s and chopping sideways.

And then we move into phase four, which is when the company starts to bottom.

The stock starts to bottom in the phase four period.

And this is where the turnaround story begins or whether it's a value trap.

The new management operating plan is rolled out in an attempt to turn around the company.

And you can see phase four lasts from somewhere in the region of towards the end of 2017 all the way up to 2020.

And this is quite typical of phase four scenarios.

They can occur for a long time and we can get a lot of volatility during the phase four period because it does take a long time for management operating plans to be implemented and for them to actually start working.

So from a trader's perspective, we obviously want to avoid shorting stocks in a whole.

So shorting stocks in phase four and phase five at or near the bottom.

Obviously, we don't know that at the time, but we can understand the characteristics of X growth stocks and where they are in their journey.

And we will be better off looking for other situations.

On top of that, we don't want to be trying to pick the top.

So we don't necessarily want to be in phase one, phase four or phase five.

We want to be capturing the journey when we get confirmation that the X growth is occurring.

And we're moving to a lower growth rate very rapidly.

If you look at the period here from mid to late 2016, when we have a break to the downside, that's phase two.

And then the break to the downside again in early 2017.

That's phase three.

So we want to capture those moves.

As traders and portfolio managers, we would have wanted to have captured the move in Under Armour from around high 30s dollars down to low 20s dollars.

But of course, we're not going to capture all of the move.

If we can capture half of it, two thirds of it, three quarters of it, we're doing very well.

Another example that demonstrates the progression of our shortwave template is a company called Teneco, T-E-N, which moved on the journey from being a $4 billion market cap stock at $70, becoming a $250 million stock at $3 a share.

And Teneco is in the automotive equipment market.

So we can clearly see a phase one period from the end of 2016 to around the end of the first quarter of 2018.

And then phase one, this is an area where we're probably not shorting the stock, but we're starting to see that a company could be going X growth.

And then when we actually see it break to the downside, this is where we want to be playing it and we get confirmation that the stock is now X growth.

So we would have liked to have been shorting this stock around June to September 2018 to enable us to capture the phase two move and the phase three move down in the stock.

We can also see after we have the phase three move down, we get the phase four period beginning.

So after the phase three move down, the phase four period begins in the time horizon between June and September 2019.

And you can see that the phase four period lasts a very long time, all the way up to the end of the chart, which is in around April 2021.

So almost two years the phase four period happened before the phase five period occurs.

And this is where either the turnaround happens or not.

And if you want to go and have a look at this stock, go away and have a look at it.

And you'll see that the stock rallies actually quite significantly from the $10 level up to above the $20 level in a very short space of time.

But obviously, that's not a full turnaround.

We're still in the phase five period.

But the phase five period began in April 2021.

But these are two good examples, Under Armour and Tenneco, because they're in two different market cap spaces.

So Under Armour started off as a $25 billion stock and went from being a large cap to a mid cap.

And Tenneco went from being a mid cap, a $4 billion stock to being a micro cap.

So these are good examples to use because the way we look at things as traders and portfolio managers, with our market cap limits on our shorts, we would much rather be shorting Under Armour rather than Tenneco.

Even though Tenneco may have exhibited X growth characteristics, we would much rather be short Under Armour even if Tenneco is available.

And you can also imagine in both scenarios, when Under Armour had already dropped significantly, and we were in phase four, and Tenneco had already dropped significantly, and we're in phase four or even phase five for both stocks.

We don't want to short either of them.

We want to be staying away from those types of shorts.

So we'd much rather filter for market cap and be shorter stock like Under Armour in that situation than be short in a stock like Tenneco simply because of the market cap and the gap risk.

But neither of them.

We want to be involved at phase four and phase five or even in phase one.

We want to be capturing phase two and phase three in stocks like Under Armour.

Let's have a look at a mega cap stock that is actually in phase one and has a big question mark over it.

We looked at this stock, Shopify, earlier in the video series, and we realized that revenue growth was slowing down post-2020, below 2019 and previous year levels.

And if we take a snapshot of Shopify in April 2021, we can see the stock price is $1,145.46.

It has a market cap of $165 billion.

So it's already put in a top at this stage, just above $1,400.

So the question is, is if we're seeing a fundamental slowdown of the top line and potentially a fundamental slowdown in other parts of the business relative to previous years, are we in phase one and is it going to get worse?

So the $1,400 and the $165 billion stock becomes what?

Well, at this moment in time, we just don't know.

And this is a great example as to why as traders and portfolio managers, we don't try to pick the top.

We don't try to go short stocks that haven't become confirmed X growth names yet.

If we had a fundamentally bearish tailwind in Shopify, where we're seeing evidence of top line growth falling quite aggressively, and earnings estimates from analysts being cut and the stock starts to break to the downside, perhaps below the 1,000 level.

This is where we want to start getting short to take advantage of the phase two and the phase three move, if that potentially plays out.

So Under Armour and Teneco are good examples of why we try to stay away from phase four and phase five situations, because they become turnaround stories or value traps and have a lot of volatility around that price for a long time.

And we can just get caught out being short.

Also with Under Armour and Teneco, they do display that at the moment in time of phase one, we're probably not confirmed yet that the stock is going X growth.

And we need the stock to confirm that and for it to break to the downside so we can take advantage of phase two and phase three.

And Shopify is the perfect example of why we wouldn't short something in phase one, because it's too early.

It's too early.

It's too early yet to know whether the company, whether the stock has gone X growth.

Now, what we've talked about so far in this video on short idea processing.

It's all been about fundamental earnings growth.

But when we're shorting stocks, there are technical factors that we have to take into consideration as well.

And something we always have to consider, even with long ideas as well, but especially with short ideas.

We need to consider short interest in the stock.

And a really good resource for checking short interest as a retail trader is a website called shortsqueeze.com.

You should register there.

It's well worth the small annual fee to become a member of that website because you'll be able to check short interest in any stocks that you have ideas in.

So short interest is calculated as a short interest percentage.

So that's the amount of shares that have been sold short in the market divided by the amount of shares in issue.

So the float of the company.

And what this does is give us a sentiment gauge on how bearish the market is on the stock, but a much more useful measure, even though we do need to know what short interest is all the time and be aware of it.

A more useful measure is actually the days to cover ratio.

This is a liquidity measure.

So the liquidity measure of days to cover ratio is the amount of shares that have been sold short in the market divided by the average daily volume of the stock over the last 30 days.

And what this does is tell us that if everyone in the market who is currently short the stock went into the market to buy all of their shares back, how many days would it take them to actually buy all of their stock back?

This is why it's a liquidity measure.

So, yes, we absolutely have to be aware of what the short interest percentage is, as in how many shares have been sold short as a percentage of the amount of shares in issue, the float.

That can be very, very important.

But this is more of a sentiment indicator.

But what we also have to be aware of is the liquidity measure of days to cover.

So the days to cover ratio.

This is more important because it really gives us an understanding of the actual liquidity of the short that's out there relative to the amount of volume that is trading in the stock.

So short interest when we're using it in conjunction with the days to cover ratio is both a sentiment and liquidity measure.

You should use this as part of your technical analysis for both short and long ideas.

So imagine if we have a high days to cover ratio.

This basically means that there's a big risk of a very large short squeeze that could occur in the stock when all the shorts have to buy or cover their shorts.

So when they step into the market and buy all of their shares back.

Now, both a high short interest percentage and a high days to cover ratio could also mean that we're looking at a consensus short idea that is old, that is stale, that is not an original idea.

So it's a lazy default short in the market.

So this could be a situation, for example, like a phase four or phase five scenario.

But it could also be a phase one scenario.

So this is actually a good thing for your longs.

But obviously, it's a bad thing for any shorts.

So the question here is always, what is a dangerous short interest percentage level for short ideas?

Well, with this one, there is no right answer.

I've been involved in situations where on the professional side, for example, I've seen situations where there's been 60, 70, 80% short interest in a stock.

And things are going really bad for the company and it's actually really justified because they can go bankrupt.

And I've seen situations where one hedge fund has been 35, 40% of the entire shares in issue short the stock and the stock goes to zero.

So with the percentage short interest itself for short ideas, there is no right answer here as to a level that is dangerous.

It always has to be taken in the context of what's actually happening with the stock.

In that situation, for example, where one hedge fund is short 35, 40% of all the shares in issue and the total short interest is 70, 80% of all shares in issue.

In that situation, the stock is cratering and it's generally in situations like that trading its market cap every day or even more than the value of its market cap every day.

So there's a lot of liquidity in the stock as it's traveling towards zero.

So the days to cover ratio in a situation like that might be surprisingly low.

So with percentage short interest, you can't look at it and say just because it's 15% or 25% or 45% or 65% that it's high.

And there's a liquidity issue.

The liquidity issue is captured by the days to cover ratio.

With the short interest percentage, that is more of a sentiment issue.

It gives you a gauge on how hated the stock is by the market, how bearish the market is.

The days to cover ratio tells you if there's a liquidity issue with the shorts.

So obvious question, what is a dangerous days to cover ratio for shorts?

Well, as a liquidity measure for S&P 500 stocks.

So fairly big stocks, large cap and mega cap stocks above 15 days starts to become marginal.

And once you start getting into the 20 day area, it starts to get dangerous and above 30 days, it officially is dangerous.

So the way you've got to think about it is this.

When you look at the formula of the days to cover ratio, which is the amount of shares sold short over the average daily volume of the stock for the last 30 days.

This formula is assuming that if everybody in the market went into the market to buy their shorts back, that they're going to be 100% of the volume on an average day, which obviously technically can't be the case.

A more likely scenario is that they're going to be 20, 25, 30, 33% of the volume, something like this.

So imagine if you see a days to cover ratio of 20 days in a stock, what does that really mean?

Well, that 20 days assumes that if all the shorts went into the market to buy all of their stock back to cover their shorts, that it would take them 20 days based on the average daily volume of the last 30 days.

But in reality, that can't happen.

They can't be 100% of the volume.

So let's assume that they went into the market and they were 25% of the day's volume.

That means it would take them 80 trading days for all the shorts to cover their positions.

So you have to think of the short interest percentage as a sentiment indicator and the days to cover ratio as a liquidity measure.

And think of the days to cover ratio in terms of order flow.

So in terms of unwinds, so unwinding as a percentage of the volume.

So this is why, for example, in periods like phase four and phase five of our short wave template, we try to avoid being the hero and shorting stocks based on past information, thinking that fundamentals are just going to continually get worse and the stock is going to zero.

We don't need to be the heroes in shorting stocks to zero.

We can find and be happy with shorting stocks in phase two and phase three.

Because often what you will find with stocks in phase four and phase five is that there's a lot of consensus short positioning and technically the market can get itself in a bit of a mess or a big mess by getting short.

Too many shares as a percentage of the amount of shares in issue and relative to the average daily volume of the stock.

So when the company starts making noises, some positive noises around a possible turnaround story, we can get big short squeezes in the stock where everyone has to go in and buy the stock all at the same time to cover their shorts.

But they cut because there's no liquidity in the stock for the amount of shares that have been sold short in the market from the consensus positioning.

But in the year 2021, we saw some examples of this play themselves out in the market where the victims of the short interest were actually on the professional side of the industry.

So I'm sure you've all heard of the GameStop GME fiasco.

Here, there's a screenshot that we took in April 2021 where we're just capturing in this screenshot the amount of shares outstanding and the float of the company.

We can also see that the share price is currently $186.95.

The short interest percentage of the float is 10.2 million shares, which makes 18.84% of the float.

And we also have a days to cover ratio of roughly one third of a day to cover that short.

So roughly back of the envelope, the amount of shares that were changing hands each day must have been around 30 million shares.

But what we can also get and what is interesting is to look at the history of the short interest level, the amount of shares that have been sold short in the market, the history of that.

And we can see back in December 2020, going back for a period of at least four or five months where we can see that the total level of shares that were sold short in the market is around 70 million shares.

Which is equivalent, which is equivalent, as we know from the screenshot taken on the previous screen, which is equivalent to the total amount of shares in issue, the amount of shares outstanding.

So it's equivalent to the entire market cap of the company.

Now, GameStop GME as a stock was for a long time on a long, slow decline as a stock, as a company, fundamentally, and had gone well beyond its X growth phase and was in the phase five scenario.

So what we would characterize as the phase five scenario.

And they were in the phase five scenario for a very long time.

As in, it was a potential turnaround or value trap for an extremely long time.

And the turnaround just never happened over and over and over again.

And some smart ass in the professional training world on the hedge fund side decided that this stock stays were over.

It's going to zero.

It's going to zero.

And he wanted to be the hero.

And he forgot about all his basic principles of shorting and decided to end up shorting a significant percentage of the amount of shares in issue.

And as the stock started to creep up, he just got shorter and shorter and shorter, convinced that the stock was going to zero.

The company was bankrupt.

It was never going to turn around.

And he was trying to be the hero.

Well, guess what happened to that guy?

Here's the stock.

In January 2021, some retail traders in the fourth quarter of 2020 got onto this and decided that GME GameStop presented value with some potential upside.

And that there was a crowded short in the market that could be exploited.

And they went and bought some stock and then distributed the trade idea on public forums.

And then lots of retail traders came in to buy stock and call options.

And the stock started rallying aggressively in the second week of January 2021.

And just a few weeks later, the stock had gone from essentially $10, $20 a share above $400 a share.

So the hedge fund that was short, the majority of the shares outstanding in the market got absolutely killed.

And a lot of retail traders made good money on that trade.

So in October 2020, GameStop was trading below $10 a share.

And at $10 a share, their market cap was around $700 million.

The short interest in the stock from April 2020 to August 2020 was roughly between $50 million to $60 million shares sold short of the $70 million shares outstanding.

And as we can see from the previous chart that we looked at, short interest continued to rise as the stock rose to $70 million shares.

So the hedge funds, and there was one main hedge fund that was the majority of the short.

So the hedge funds that were short, they were essentially short the equivalent of the entire market cap of the company.

So all the shares in issue.

Now being short $50 to $60 million of the $70 million shares outstanding is totally irresponsible to begin with.

But even worse, they were getting shorter and shorter as the stock rose to try and defend the short and sit on the stock so it wouldn't rally and the rally wouldn't kill them.

So what lessons can we take from this?

Well, shorting stocks in a hole and going for the hero trade is not something we want to be involved in ever.

No matter how convinced you are, we should be staying away from these phase four and phase five situations.

We don't need to expose ourselves to the hero to zero trade.

We don't need to expose ourselves to the hero trade.

We can be quite happy to be playing the phase two and phase three moves over a shorter time horizon.

And this is again why we have a market cap limit on shorts, because essentially a market cap limit is also a liquidity limit.

So when you're generating short ideas and you see X growth companies that are fundamentally a short, so you have the earnings growth profiles, you've done further work, and you believe the stock is going to go lower and it's a phase two and phase three situation.

And if it's a green light and it's acceptable, of course, you can go ahead and short the stock if it's genuinely X growth and in the phase two and phase three scenarios.

However, if you see fundamentals in the earnings growth that are questionable, you pull up the stock and it's down a lot already.

It seems to be in the phase four period.

Management are making noises about a turnaround and a new operating plan, a new management operating plan.

You check the short interest percentage and it's very high.

You check the days to cover and it's above 15, perhaps above 20, even worse above 30.

You check the short interest rate.

This is an issue.

These are the types of short ideas that we want to stay away from.

Why?

Because we will end up like this donut at Melvin Capital.

Gabe Plotkin, who was the guy behind the GME short.

Yes, they were down 49% on their entire fund in the first quarter of 2021, which is an irrecoverable position, even for a professional hedge fund manager.

That is an absolute disaster.

For a retail trader, 49% in a quarter loss as well is a disaster.

So these are the situations that we need to stay away from.

Stay away from the scenarios that are phase four and phase five.

Try not to get into bad habits of trying to short stocks in a hole and being the hero thinking that you've got an edge over the market and that a stock that's already down 80% is going to deteriorate further and go to zero.

And you're the hero calling it and you're going to be the guy that makes all the money.

Make sure you stay away from those situations.

Also, make sure that you stay away from bad habits of shorting stocks too early in phase one.

Try to tend towards good behaviors of shorting stocks in phase two, taking advantage of a phase two move and taking advantage of a phase three move and then move on to the next one.

So we always need to use short interest percentage and the days to cover ratio as a head check on our fundamental work to figure out what the technical situation is in the market before even thinking about initiating a position.

Now, does this mean that we should use short interest percentage and days to cover as a way to find long ideas and short ideas?

So for example, you rank short interest percentage and days to cover numbers via the website shortsqueeze.com and you just simply go long, high short interest names and short, low short interest names.

Well, no, of course not.

This is not how we generate trade ideas.

This is just one tiny part of the overall process that may allow you to avoid or swerve traps and or to confirm that your potential idea is not consensus.

So always, always, always make sure of the short interest percentage and the days to cover ratio when you've generated what you believe is a fundamentally driven short idea.

You need to check the technical situation in the market with short interest percentage and days to cover.

Now, something else that you need to check as a technical situation as well is whether a company is paying a dividend or not.

This becomes quite important even in the 20 to 60 day time horizon.

So if a company is paying a dividend within that time horizon, it becomes quite important as a technical situation to consider.

So the questions you need to ask yourself are, is a company actually paying a dividend or not?

If they are, how much is the dividend in terms of cents per share and also as a percentage yield?

And also, what is the likelihood that the company is going to cut their dividend?

Now, the reason why this is important is because when you are short a dividend paying stock, you are actually what is termed short the dividend.

You are a borrower of stock from a stock owner and you will owe them the dividend.

Now, in reality, in your trading account, you won't actually have to physically take any action at all.

The broker should do everything for you on your behalf.

So running through an example, let's say we have a $100 stock that pays a dividend of $1 per quarter.

So they're paying $4 over the year, $4 in total, 4% dividend yield.

Now, let's say you've identified this stock as a potential fundamental short.

So after all your hard work of identifying the stock as a short, you decide that you're going to short a hundred shares of this $100 stock.

So your position is going to be $10,000 notional or gross exposure.

Now, let's say the stock goes down $10 to $90 a share before the next ex-dividend date.

So this is great.

This is a good situation because you're short at $100.

Congratulations.

You're making money.

Your position is now 100 shares short at $100, showing a profit of $1,000.

And your mark-to-market gross exposure is 100 shares at $90.

So $9,000 notional gross exposure that's marked to market.

Now, on the next quarterly ex-dividend day, you open your brokerage platform and the stock has gone what we call ex-dividend by the $1 dividend per share.

And your average price that you are short, originally from $100, has now gone to $99 in the trading platform, in your trading account.

And the stock opens $1 lower that day at $89.

So in the new situation, what's your position?

What's your profit or loss?

What is your actual gross exposure?

Well, your position is still short 100 shares, but now you have an average price of being short at $99.

So with the stock at $89, you're still up $10 on 100 shares short.

So your P&L is still up $1,000.

But your gross exposure is now 100 shares mark-to-market at $89.

So $8,900.

So this is because the stock has now gone ex-dividend by $1.

So they've paid out a quarterly dividend of the $1 per share.

And this money leaves the company balance sheet.

On the ex-dividend date, the stock adjusts lower by $1 to reflect the value of the dividend that's been paid out to the stock owners, the shareholders.

So for yourself who is short as a person or entity that has a short position, you do not own the stock.

And therefore, you don't receive the dividend.

So the $1 per share.

So your average price adjusts to reflect the fact that you didn't receive it.

On the long side, the owner of the stock that you owe the dividend to receives the $1 per share dividend at some point in the future on the dividend payable or settlement date.

And the owner of the stock has their average price adjusted down also by $1.

However, they actually receive the $1 payment into their trading account at the settlement date.

As the short seller, you don't receive any payment.

So for the stock owner, the trade is simply a wash.

There's a $1 stock adjustment and $1 average price adjustment.

For a person or entity who is short, it's just an average price adjustment.

So let's make this a little bit more clear.

Imagine if you kept the short position on for a decade, for 10 years, what would actually happen?

Well, for the company, there would be $41 dividend payments made to shareholders in that period because it's a quarterly $1 dividend.

So let's say the stock over the 10 years goes from $100 to $200 in terms of appreciation.

Well, the owner of the shares receives $40 in dividends realized and has made $100 unrealized in terms of capital gain on the stock's appreciation.

So the owner's new average price, because they're receiving all of these 40 dividends, these $41 dividends, the owner's new average price is $60.

So on an initial investment of 100 shares at $100, so the $10,000 notional, they've made a profit of $140 per share with 100 shares.

So it's $14,000 profit on top of the $10,000 initial investment.

The short seller of 100 shares over the same time period loses $40 in value of dividend value because they didn't receive the dividend as a realized payment.

So the short seller's new average price is also $60 but they didn't receive any dividends.

So they have an unrealized loss of $140 per share or $40,000 on the initial short of the notional $10,000.

Now, on the actual ex-dividend date that a stock goes ex-dividend, typically, but not all the time, stocks will go higher than their ex-dividend adjustment price.

And this is mainly because a lot of shareholders elect to automatically reinvest the dividend back into the stock.

So from the example that we've been going through, the owner that received the $100 dividend when the stock was at $89 at the ex-dividend adjustment price, they may have elected to automatically buy one share at $89.

Now, if all the owners of the stock do this, then the stock will likely not go down on the ex-dividend date and will be up, potentially when even buyers break limit.

So we term this by saying the stock went ex-dividend.

Well, so on the ex-dividend date, the stock actually went up above the ex-dividend adjustment price.

If the stock closes lower than the adjustment price of $89, we term this as the stock went ex-dividend badly.

So a stock can go ex-dividend well or badly for multiple other reasons.

There are many variables at play here.

So for example, when the US stock market is closed, if a company is or a stock is going ex-dividend the following day and overnight, for example, overseas markets, the wider stock markets may have just been up really big overnight.

And the stock could just open up the next day in the US at $92 with a dividend adjustment price of $89.

So it could be up $3 on the ex-dividend day for that reason.

It doesn't really matter what the reason is.

If the stock closes on the ex-dividend day above $89, so our ex-dividend adjustment price, the stock still went ex-dividend well.

Below $89, the stock simply went ex-dividend badly.

So does this mean as a short seller that you should always avoid being short dividend paying stocks?

Well, no, of course not.

If the business operation of the company is cratering, then the dividend is likely to get cut and could be cut entirely.

So the stock in anticipation of that could just get absolutely hammered and the dividend just doesn't even matter.

So if you're looking to short a dividend paying stock, then you have to have a good or high level of conviction that the dividend is actually going to get cut.

So as with short interest percentage and with the days to cover ratio, we have to have a head check also for the technical situation in the market with the company's dividend if they're paying a dividend at all.

And we need to ask ourselves the pretty serious questions that are actually very simple and straightforward to answer.

Firstly, is the company paying a dividend?

Secondly, how much?

And third, what is the likelihood that the company is going to cut the dividend?

So we must have this process in place as a head check additional to short interest and days to cover to make sure we're happy being short a stock that actually pays a dividend.

And the amount of the dividend and the likelihood so we're actually happy that we're doing it.

So have your fundamentally driven short trade idea in place.

Check the short interest percentage.

Check the days to cover ratio.

Check the dividend situation.

Are they paying a dividend?

How much and what's the likelihood that they're going to cut the dividend based on my analysis of the business operation?

If all of those are in place and you're happy with the situation, you're happy with the fundamentals and happy with the short interest, days to cover and dividend situation, then your short trade idea probably has a green light.

But remember, we still have a lot more work to do in the trade idea generation process for shorts and as well as longs.

We don't just get our trade ideas by ranking for earnings growth and then go long and short stocks.

But we obviously have to do a lot more work on the companies to see what's behind earnings growth, valuation, etc.

Remember when we're looking at the earnings growth profiles in a sector like we have done and characterized the earnings growth profiles in this video from a short perspective through a short lens.

This is an identification process.

We continue to do more work once we have identified what we believe to be negative outliers in a particular sector and our further work will determine whether we believe our trade idea is actually a green light and is actually a short.

So let's summarize everything here for short idea processing.

So for our quant processes on identifying potential short ideas, we outlined the earnings growth profiles that we look for.

Now, sequentially negative earnings growth is ideal in quotes on paper.

However, in a GDP growth environment, it is much harder to find than if we were in a GDP slowdown or an expected GDP contraction environment.

In addition to that, we also have to consider that if EPS growth expectations have already been set in the market at sequentially negative as a profile, it is very likely that the stock has already moved quite a bit lower.

So what we want to be doing as traders is targeting the phase two and phase three scenarios on the journey of a stock falling.

We will most probably find ourselves going for the next best thing after sequentially negative earnings growth profiles in our list.

So cases number two, three, four and five as long as we are in what we characterized as a phase two or phase three scenario of stock price decline on its journey on the way down.

We also have to add market cap filters on our shorts to avoid making the rookie errors of, for example, like shorting stocks in a hole and going for the zero to hero trade.

Additionally, we have to overlay our fundamental work with technical factors in our process in the quantum phase, for example, checking the short interest days to cover ratio and the dividend situation.

Most importantly, out of the technical factors, we want to make sure that we are not exposing ourselves to high levels of short interest.

So high levels of short interest and high days to cover, which basically is a warning sign that we could be entering or getting sucked into consensus market positioning.

So high levels of short interest that indicate extreme bearish sentiment that's already occurring in the market.

And also on top of that, a very high days to cover ratio, which means there could be a liquidity issue and we could get a short squeeze in the stock and get caught out.

At the end of the day, we are traders, not investors.

Catching the phase two and phase three scenario in an X growth stock is what we are looking to achieve with our short ideas.

We are seeking to predict and participate in a fundamental shift lower in expectations of the business operation.

To achieve earnings, we want to achieve earnings EPS, earnings growth and even revenue growth as well.

And as always, just like with long ideas, we want to be catching the 20 to 60 day time horizon.

And with shorts, what we want to be focusing on is attempting to catch the sharp moves down in the stock during those phase two and phase three periods.

So that about wraps it up for this video with short idea processing in the quant phase.

I don't think we need a summary again by going back to the desk for this one.

Let's go right in to the next video where we're going to be looking at turnaround stories and value traps.
